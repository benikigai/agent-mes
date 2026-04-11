"""AgentMES web renderer — FastAPI + SSE + browser kanban.

A second consumer of the pipeline's events_callback, parallel to the
terminal Dashboard. The pipeline + 7 stages + stubs are unchanged; this
package wires them to a FastAPI app that publishes StageEvents over
Server-Sent Events to a vanilla HTML/CSS/JS frontend.
"""
