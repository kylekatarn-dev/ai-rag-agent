"""
Real Estate Agent Chain.

Main conversational agent with optimized prompts and context management.
Uses incremental summarization + lead checklist to maintain context.
"""

import json
import asyncio
from typing import Generator, AsyncGenerator, Optional
from uuid import uuid4

from openai import OpenAI, AsyncOpenAI

from app.config import OPENAI_API_KEY, OPENAI_MODEL
from app.models.lead import Lead
from app.models.conversation import ConversationState
from app.rag.retriever import PropertyRetriever
from app.scoring.lead_scorer import LeadScorer
from app.output.broker_summary import generate_broker_summary
from app.utils import get_logger, with_retry, validate_message
from .prompts import (
    EXTRACTION_PROMPT,
    SUMMARY_PROMPT,
    CONVERSATION_SUMMARY_PROMPT,
    classify_intent,
    should_extract,
    get_full_system_prompt,
)
from .tools import TOOLS

# Optional RAG memory import
try:
    from app.memory import get_chat_memory, ChatMemory
    RAG_MEMORY_AVAILABLE = True
except ImportError:
    RAG_MEMORY_AVAILABLE = False
    ChatMemory = None

logger = get_logger(__name__)


class RealEstateAgent:
    """
    Main conversational agent for real estate assistance.

    Features:
    - Phase-aware conversation management
    - Conditional extraction (skip for acknowledgments)
    - Lead checklist (prevents duplicate questions)
    - Incremental conversation summarization
    - Optional RAG-based chat memory for very long conversations
    - Async support for concurrent requests
    - Lead scoring and qualification
    """

    # Summarize conversation every N messages
    SUMMARIZE_EVERY = 8

    def __init__(self, session_id: Optional[str] = None, use_rag_memory: bool = False):
        """
        Initialize agent.

        Args:
            session_id: Optional session ID for persistence
            use_rag_memory: Enable RAG-based chat memory (default: False)
        """
        logger.info("Initializing RealEstateAgent")
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.async_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        self.model = OPENAI_MODEL
        self.retriever = PropertyRetriever()
        self.scorer = LeadScorer()
        self.state = ConversationState()
        self.session_id = session_id or str(uuid4())
        self.conversation_id = str(uuid4())

        # Incremental conversation summary
        self.conversation_summary = ""
        self.last_summarized_at = 0

        # Optional RAG-based chat memory (for very long conversations)
        self.use_rag_memory = use_rag_memory and RAG_MEMORY_AVAILABLE
        self.memory = None
        if self.use_rag_memory:
            self.memory = get_chat_memory(self.session_id)
            logger.info(f"RAG memory enabled for session {self.session_id}")

        # Build tool schemas for OpenAI
        self.tool_schemas = self._build_tool_schemas()
        logger.debug(f"Loaded {len(self.tool_schemas)} tools")

    def _build_tool_schemas(self) -> list[dict]:
        """Convert LangChain tools to OpenAI function schemas."""
        schemas = []
        for tool in TOOLS:
            schema = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    }
                }
            }

            # Extract parameters from tool signature
            if hasattr(tool, 'args_schema') and tool.args_schema:
                for field_name, field_info in tool.args_schema.model_fields.items():
                    param_type = "string"
                    if field_info.annotation == int:
                        param_type = "integer"
                    elif field_info.annotation == bool:
                        param_type = "boolean"

                    schema["function"]["parameters"]["properties"][field_name] = {
                        "type": param_type,
                        "description": field_info.description or "",
                    }

                    if field_info.is_required():
                        schema["function"]["parameters"]["required"].append(field_name)

            schemas.append(schema)

        return schemas

    def reset(self):
        """Reset conversation state and memory."""
        logger.info("Resetting conversation state")
        self.state = ConversationState()
        self.conversation_id = str(uuid4())

        # Reset conversation summary
        self.conversation_summary = ""
        self.last_summarized_at = 0

        # Reset RAG memory if enabled
        if self.memory:
            self.memory.clear_session()
            logger.info("RAG memory cleared")

    def _determine_phase(self) -> str:
        """
        Determine current conversation phase based on state.

        Returns:
            Phase name string
        """
        lead = self.state.lead
        msg_count = self.state.message_count

        # Initial greeting
        if msg_count == 0:
            return "greeting"

        # Has contact and shown properties - ready for handoff
        if lead.has_contact_info and self.state.recommendations_made:
            if lead.wants_broker_contact or lead.scheduled_meeting:
                return "handoff"
            return "contact_capture"

        # Has shown properties
        if self.state.search_performed:
            # Check for objections
            if lead.key_objections:
                return "objection_handling"
            # Ready to recommend
            if len(self.state.properties_shown) >= 3:
                return "recommendation"
            return "property_search"

        # Gathering info
        if lead.property_type or lead.preferred_locations:
            return "needs_discovery"

        return "greeting"

    def _maybe_summarize_conversation(self):
        """
        Summarize older messages if conversation is getting long.

        Called before each response to maintain manageable context.
        """
        msg_count = self.state.message_count

        # Only summarize if we have enough new messages since last summary
        if msg_count - self.last_summarized_at < self.SUMMARIZE_EVERY:
            return

        # Get messages to summarize (older ones, not the most recent)
        all_messages = self.state.messages
        if len(all_messages) <= 6:
            return  # Not enough to summarize

        # Summarize messages from last summary point to recent (keep last 4)
        start_idx = max(0, self.last_summarized_at)
        end_idx = len(all_messages) - 4  # Keep last 2 turns intact

        if end_idx <= start_idx:
            return

        messages_to_summarize = all_messages[start_idx:end_idx]

        # Format messages for summarization
        messages_text = "\n".join(
            f"{'Klient' if m.role == 'user' else 'Asistent'}: {m.content[:200]}"
            for m in messages_to_summarize
        )

        try:
            response = self._call_openai(
                messages=[{
                    "role": "user",
                    "content": CONVERSATION_SUMMARY_PROMPT.format(messages=messages_text)
                }],
            )

            new_summary = response.choices[0].message.content.strip()

            # Append to existing summary
            if self.conversation_summary:
                self.conversation_summary = f"{self.conversation_summary}\n\n{new_summary}"
            else:
                self.conversation_summary = new_summary

            self.last_summarized_at = end_idx
            logger.info(f"Summarized messages {start_idx}-{end_idx}, total summary length: {len(self.conversation_summary)}")

        except Exception as e:
            logger.warning(f"Failed to summarize conversation: {e}")

    def chat(self, user_message: str) -> Generator[str, None, None]:
        """
        Process user message and generate response.

        Yields response chunks for streaming.
        """
        # Validate and sanitize input
        sanitized_message, error = validate_message(user_message)
        if error:
            logger.warning(f"Input validation failed: {error}")
            yield f"Omlouvam se, {error}"
            return

        logger.info(f"Processing user message: {sanitized_message[:100]}...")

        # Classify intent for optimization
        intent = classify_intent(sanitized_message)
        logger.debug(f"Classified intent: {intent}")

        # Add user message to state
        self.state.add_message("user", sanitized_message)

        # Conditional extraction - skip for pure acknowledgments
        if should_extract(sanitized_message):
            self._extract_requirements(sanitized_message)
        else:
            logger.debug("Skipping extraction for short/ack message")

        # Determine conversation phase
        phase = self._determine_phase()
        self.state.current_phase = phase
        logger.debug(f"Conversation phase: {phase}")

        # Check if we need to summarize older messages
        self._maybe_summarize_conversation()

        # Build system prompt with lead checklist and conversation summary
        system_prompt = get_full_system_prompt(
            self.state.lead,
            phase,
            self.conversation_summary,
        )

        # For long conversations: use summary + recent messages
        # For short conversations: use full history
        if self.state.message_count > self.SUMMARIZE_EVERY:
            # Keep last 6 messages (3 turns) + rely on summary for older context
            recent_messages = self.state.get_messages_for_llm()[-6:]
            messages = [
                {"role": "system", "content": system_prompt},
                *recent_messages
            ]
            logger.debug(f"Using summary + {len(recent_messages)} recent messages")
        else:
            # Short conversation - use full history
            messages = [
                {"role": "system", "content": system_prompt},
                *self.state.get_messages_for_llm()
            ]

        # Optional RAG memory for additional context retrieval
        if self.memory and self.state.message_count > 10:
            memory_context = self.memory.get_relevant_context(sanitized_message)
            if memory_context:
                # Append to system prompt as additional context
                messages[0]["content"] += f"\n\n## DODATECNY KONTEXT\n{memory_context}"

        try:
            # Call OpenAI with tools
            response = self._call_openai_streaming(messages)

            # Collect response
            full_response = ""
            tool_calls = []
            current_tool_call = None

            for chunk in response:
                delta = chunk.choices[0].delta

                # Handle content
                if delta.content:
                    full_response += delta.content
                    yield delta.content

                # Handle tool calls
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        if tc.index is not None:
                            if current_tool_call is None or tc.index != current_tool_call.get("index"):
                                if current_tool_call:
                                    tool_calls.append(current_tool_call)
                                current_tool_call = {
                                    "index": tc.index,
                                    "id": tc.id or "",
                                    "name": "",
                                    "arguments": "",
                                }

                            if tc.id:
                                current_tool_call["id"] = tc.id
                            if tc.function:
                                if tc.function.name:
                                    current_tool_call["name"] = tc.function.name
                                if tc.function.arguments:
                                    current_tool_call["arguments"] += tc.function.arguments

            if current_tool_call:
                tool_calls.append(current_tool_call)

            # Execute tool calls if any
            if tool_calls:
                logger.info(f"Executing {len(tool_calls)} tool calls")
                for tc in tool_calls:
                    logger.debug(f"Executing tool: {tc['name']}")
                    tool_result = self._execute_tool(tc["name"], tc["arguments"])

                    # Track search
                    if tc["name"] in ["search_properties", "show_top_properties"]:
                        self.state.search_performed = True
                        yield f"\n\n*Vyhledavam v databazi...*\n\n"

                    # Add assistant message with tool call
                    messages.append({
                        "role": "assistant",
                        "content": full_response,
                        "tool_calls": [{
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": tc["arguments"],
                            }
                        }]
                    })

                    # Add tool response
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": tool_result,
                    })

                    # Generate follow-up response based on tool results
                    follow_up = self._call_openai_streaming(messages)

                    for chunk in follow_up:
                        if chunk.choices[0].delta.content:
                            content = chunk.choices[0].delta.content
                            full_response += content
                            yield content

            # Save assistant response
            self.state.add_message("assistant", full_response)

            # Store turn in RAG memory
            if self.memory:
                extracted_info = {
                    "property_type": self.state.lead.property_type,
                    "locations": self.state.lead.preferred_locations,
                    "min_area": self.state.lead.min_area_sqm,
                    "max_area": self.state.lead.max_area_sqm,
                    "max_price": self.state.lead.max_price_czk_sqm,
                    "name": self.state.lead.name,
                    "email": self.state.lead.email,
                    "phone": self.state.lead.phone,
                }
                self.memory.add_turn(
                    user_message=sanitized_message,
                    assistant_response=full_response,
                    extracted_info=extracted_info,
                )

            # Update lead score
            self._update_lead_score()

            logger.debug(f"Response generated, lead score: {self.state.lead.lead_score}")

        except Exception as e:
            logger.error(f"Error in chat processing: {e}", exc_info=True)
            error_msg = "Omlouvam se, doslo k chybe. Zkuste to prosim znovu."
            self.state.add_message("assistant", error_msg)
            yield error_msg

    async def achat(self, user_message: str) -> AsyncGenerator[str, None]:
        """
        Async version of chat for concurrent request handling.

        Yields response chunks for streaming.
        """
        # Validate and sanitize input
        sanitized_message, error = validate_message(user_message)
        if error:
            logger.warning(f"Input validation failed: {error}")
            yield f"Omlouvam se, {error}"
            return

        logger.info(f"Processing user message (async): {sanitized_message[:100]}...")

        # Classify intent
        intent = classify_intent(sanitized_message)
        self.state.add_message("user", sanitized_message)

        # Conditional extraction
        if should_extract(sanitized_message):
            await self._aextract_requirements(sanitized_message)

        # Determine phase
        phase = self._determine_phase()
        self.state.current_phase = phase

        # Check if we need to summarize
        self._maybe_summarize_conversation()

        # Build system prompt with lead checklist and conversation summary
        system_prompt = get_full_system_prompt(
            self.state.lead,
            phase,
            self.conversation_summary,
        )

        # For long conversations: use summary + recent messages
        if self.state.message_count > self.SUMMARIZE_EVERY:
            recent_messages = self.state.get_messages_for_llm()[-6:]
            messages = [
                {"role": "system", "content": system_prompt},
                *recent_messages
            ]
        else:
            messages = [
                {"role": "system", "content": system_prompt},
                *self.state.get_messages_for_llm()
            ]

        # Optional RAG memory
        if self.memory and self.state.message_count > 10:
            memory_context = self.memory.get_relevant_context(sanitized_message)
            if memory_context:
                messages[0]["content"] += f"\n\n## DODATECNY KONTEXT\n{memory_context}"

        try:
            # Call OpenAI async
            response = await self._acall_openai_streaming(messages)

            full_response = ""
            tool_calls = []
            current_tool_call = None

            async for chunk in response:
                delta = chunk.choices[0].delta

                if delta.content:
                    full_response += delta.content
                    yield delta.content

                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        if tc.index is not None:
                            if current_tool_call is None or tc.index != current_tool_call.get("index"):
                                if current_tool_call:
                                    tool_calls.append(current_tool_call)
                                current_tool_call = {
                                    "index": tc.index,
                                    "id": tc.id or "",
                                    "name": "",
                                    "arguments": "",
                                }
                            if tc.id:
                                current_tool_call["id"] = tc.id
                            if tc.function:
                                if tc.function.name:
                                    current_tool_call["name"] = tc.function.name
                                if tc.function.arguments:
                                    current_tool_call["arguments"] += tc.function.arguments

            if current_tool_call:
                tool_calls.append(current_tool_call)

            # Execute tools
            if tool_calls:
                for tc in tool_calls:
                    tool_result = self._execute_tool(tc["name"], tc["arguments"])

                    if tc["name"] in ["search_properties", "show_top_properties"]:
                        self.state.search_performed = True
                        yield f"\n\n*Vyhledavam v databazi...*\n\n"

                    messages.append({
                        "role": "assistant",
                        "content": full_response,
                        "tool_calls": [{
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": tc["arguments"],
                            }
                        }]
                    })

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": tool_result,
                    })

                    follow_up = await self._acall_openai_streaming(messages)
                    async for chunk in follow_up:
                        if chunk.choices[0].delta.content:
                            content = chunk.choices[0].delta.content
                            full_response += content
                            yield content

            self.state.add_message("assistant", full_response)

            # Store turn in RAG memory
            if self.memory:
                extracted_info = {
                    "property_type": self.state.lead.property_type,
                    "locations": self.state.lead.preferred_locations,
                    "min_area": self.state.lead.min_area_sqm,
                    "max_area": self.state.lead.max_area_sqm,
                    "max_price": self.state.lead.max_price_czk_sqm,
                    "name": self.state.lead.name,
                    "email": self.state.lead.email,
                    "phone": self.state.lead.phone,
                }
                self.memory.add_turn(
                    user_message=sanitized_message,
                    assistant_response=full_response,
                    extracted_info=extracted_info,
                )

            self._update_lead_score()

        except Exception as e:
            logger.error(f"Error in async chat: {e}", exc_info=True)
            error_msg = "Omlouvam se, doslo k chybe. Zkuste to prosim znovu."
            self.state.add_message("assistant", error_msg)
            yield error_msg

    @with_retry(max_retries=3, initial_delay=1.0)
    def _call_openai_streaming(self, messages: list[dict]):
        """Call OpenAI API with retry logic."""
        return self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=self.tool_schemas if self.tool_schemas else None,
            stream=True,
        )

    async def _acall_openai_streaming(self, messages: list[dict]):
        """Call OpenAI API async with streaming."""
        return await self.async_client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=self.tool_schemas if self.tool_schemas else None,
            stream=True,
        )

    @with_retry(max_retries=3, initial_delay=1.0)
    def _call_openai(self, messages: list[dict], **kwargs):
        """Call OpenAI API without streaming, with retry logic."""
        return self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            **kwargs
        )

    async def _acall_openai(self, messages: list[dict], **kwargs):
        """Call OpenAI API async without streaming."""
        return await self.async_client.chat.completions.create(
            model=self.model,
            messages=messages,
            **kwargs
        )

    def _execute_tool(self, tool_name: str, arguments: str) -> str:
        """Execute a tool by name with given arguments."""
        try:
            args = json.loads(arguments) if arguments else {}
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse tool arguments: {e}")
            args = {}

        for tool in TOOLS:
            if tool.name == tool_name:
                try:
                    result = tool.invoke(args)
                    logger.debug(f"Tool {tool_name} executed successfully")

                    # Track properties shown
                    if tool_name in ["search_properties", "show_top_properties", "get_property_details"]:
                        # Extract property IDs from result if possible
                        import re
                        ids = re.findall(r'ID[:\s]+(\d+)', result)
                        property_ids = [int(id) for id in ids]
                        self.state.properties_shown.extend(property_ids)

                        # Fetch and store actual Property objects for card display
                        if property_ids:
                            try:
                                from app.data.loader import get_property_by_id
                                properties = [get_property_by_id(pid) for pid in property_ids]
                                self.state.last_shown_properties = [p for p in properties if p]
                            except Exception as prop_e:
                                logger.warning(f"Failed to fetch properties for display: {prop_e}")

                    return result
                except Exception as e:
                    logger.error(f"Tool {tool_name} execution failed: {e}", exc_info=True)
                    return f"Chyba pri vyhledavani: {str(e)}"

        logger.warning(f"Tool {tool_name} not found")
        return f"Nastroj {tool_name} neni k dispozici."

    def _extract_requirements(self, message: str):
        """Extract requirements from user message using LLM."""
        current_info = {
            "property_type": self.state.lead.property_type,
            "min_area_sqm": self.state.lead.min_area_sqm,
            "max_area_sqm": self.state.lead.max_area_sqm,
            "locations": self.state.lead.preferred_locations,
            "max_price_czk_sqm": self.state.lead.max_price_czk_sqm,
            "move_in_urgency": self.state.lead.move_in_urgency,
            "name": self.state.lead.name,
            "email": self.state.lead.email,
            "phone": self.state.lead.phone,
            "company": self.state.lead.company,
            "preferred_contact_method": self.state.lead.preferred_contact_method,
            "wants_notifications": self.state.lead.wants_notifications,
            "wants_broker_contact": self.state.lead.wants_broker_contact,
        }

        try:
            response = self._call_openai(
                messages=[{
                    "role": "user",
                    "content": EXTRACTION_PROMPT.format(
                        message=message,
                        current_info=json.dumps(current_info, ensure_ascii=False)
                    )
                }],
                response_format={"type": "json_object"},
            )

            result = json.loads(response.choices[0].message.content)
            logger.debug(f"Extraction result: {result}")

            # Check if there's new info
            if not result.get("has_new_info", True):
                logger.debug("No new info extracted")
                return

            extracted = result.get("extracted", {})

            # Update lead with extracted info
            lead = self.state.lead
            self._apply_extraction(lead, extracted)

            # Handle corrections
            corrections = result.get("corrections", {})
            if corrections:
                logger.debug(f"Applying corrections: {corrections}")
                self._apply_extraction(lead, corrections)

            # Track objections
            if result.get("detected_objection"):
                lead.key_objections.append(result["detected_objection"])

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse extraction response as JSON: {e}")
        except Exception as e:
            logger.error(f"Requirement extraction failed: {e}", exc_info=True)

    async def _aextract_requirements(self, message: str):
        """Async version of extract requirements."""
        current_info = {
            "property_type": self.state.lead.property_type,
            "min_area_sqm": self.state.lead.min_area_sqm,
            "max_area_sqm": self.state.lead.max_area_sqm,
            "locations": self.state.lead.preferred_locations,
            "max_price_czk_sqm": self.state.lead.max_price_czk_sqm,
            "move_in_urgency": self.state.lead.move_in_urgency,
            "name": self.state.lead.name,
            "email": self.state.lead.email,
            "phone": self.state.lead.phone,
            "company": self.state.lead.company,
        }

        try:
            response = await self._acall_openai(
                messages=[{
                    "role": "user",
                    "content": EXTRACTION_PROMPT.format(
                        message=message,
                        current_info=json.dumps(current_info, ensure_ascii=False)
                    )
                }],
                response_format={"type": "json_object"},
            )

            result = json.loads(response.choices[0].message.content)

            if not result.get("has_new_info", True):
                return

            extracted = result.get("extracted", {})
            self._apply_extraction(self.state.lead, extracted)

            corrections = result.get("corrections", {})
            if corrections:
                self._apply_extraction(self.state.lead, corrections)

            if result.get("detected_objection"):
                self.state.lead.key_objections.append(result["detected_objection"])

        except Exception as e:
            logger.error(f"Async extraction failed: {e}", exc_info=True)

    def _apply_extraction(self, lead: Lead, data: dict):
        """Apply extracted data to lead model."""
        if data.get("property_type"):
            lead.property_type = data["property_type"]
        if data.get("min_area_sqm"):
            lead.min_area_sqm = data["min_area_sqm"]
        if data.get("max_area_sqm"):
            lead.max_area_sqm = data["max_area_sqm"]
        if data.get("locations"):
            lead.preferred_locations = data["locations"]
        if data.get("max_price_czk_sqm"):
            lead.max_price_czk_sqm = data["max_price_czk_sqm"]
        if data.get("move_in_urgency"):
            lead.move_in_urgency = data["move_in_urgency"]
        if data.get("name"):
            lead.name = data["name"]
        if data.get("email"):
            lead.email = data["email"]
        if data.get("phone"):
            lead.phone = data["phone"]
        if data.get("company"):
            lead.company = data["company"]
        if data.get("preferred_contact_method"):
            lead.preferred_contact_method = data["preferred_contact_method"]
        if data.get("wants_notifications"):
            lead.wants_notifications = data["wants_notifications"]
            if lead.wants_notifications:
                lead.notification_criteria = lead.to_search_criteria()
        if data.get("wants_broker_contact"):
            lead.wants_broker_contact = data["wants_broker_contact"]

    def _update_lead_score(self):
        """Update lead score based on current state."""
        # Get matched properties if we have enough info
        matched = []
        if self.state.has_enough_info_for_search:
            try:
                matched = self.retriever.search_properties(
                    property_type=self.state.lead.property_type,
                    locations=self.state.lead.preferred_locations,
                    min_area=self.state.lead.min_area_sqm,
                    max_area=self.state.lead.max_area_sqm,
                    max_price=self.state.lead.max_price_czk_sqm,
                    top_k=5,
                )
            except Exception as e:
                logger.warning(f"Property search failed during score update: {e}")

        # Score the lead
        self.scorer.score_lead(self.state.lead, matched)
        logger.debug(
            f"Lead score updated: {self.state.lead.lead_score} "
            f"({self.state.lead.lead_quality.value})"
        )

    def get_lead(self) -> Lead:
        """Get current lead data."""
        return self.state.lead

    def get_lead_score(self) -> int:
        """Get current lead score."""
        return self.state.lead.lead_score

    def get_memory_stats(self) -> dict:
        """Get memory and context statistics."""
        stats = {
            "total_messages": self.state.message_count,
            "summary_length": len(self.conversation_summary),
            "last_summarized_at": self.last_summarized_at,
            "has_summary": bool(self.conversation_summary),
        }

        # Add RAG memory stats if available
        if self.memory:
            rag_stats = self.memory.get_stats()
            stats["rag_memory"] = rag_stats

        return stats

    def generate_summary(self) -> str:
        """Generate broker summary for current lead."""
        logger.info("Generating broker summary")

        # Get matched properties
        matched = []
        if self.state.lead.matched_properties:
            from app.data.loader import get_property_by_id
            matched = [
                get_property_by_id(pid)
                for pid in self.state.lead.matched_properties
            ]
            matched = [p for p in matched if p]

        # Build conversation log
        conv_log = "\n".join(
            f"{'Klient' if m.role == 'user' else 'Asistent'}: {m.content}"
            for m in self.state.messages
        )

        # Generate structured summary using improved prompt
        self.state.lead.conversation_summary = self._generate_conversation_summary()

        return generate_broker_summary(
            lead=self.state.lead,
            matched_properties=matched,
            conversation_log=conv_log,
        )

    def _generate_conversation_summary(self) -> str:
        """Generate a structured summary of the conversation."""
        messages_text = "\n".join(
            f"{m.role}: {m.content}" for m in self.state.messages
        )

        try:
            response = self._call_openai(
                messages=[{
                    "role": "user",
                    "content": SUMMARY_PROMPT.format(messages=messages_text)
                }],
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Failed to generate conversation summary: {e}")
            return "Shrnuti konverzace neni k dispozici."
