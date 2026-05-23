from __future__ import annotations

from neuralclear.core import ProtocolError

from .registry_store import AgentRegistryStore


def register_registry_routes(
    app,
    registry_store: AgentRegistryStore,
    handle_error,
    protected_dependencies=None,
) -> None:
    protected_dependencies = protected_dependencies or []

    @app.post("/registry/agents", dependencies=protected_dependencies)
    def register_agent(manifest: dict[str, object]) -> dict[str, object]:
        try:
            return registry_store.register(manifest)
        except ProtocolError as exc:
            handle_error(exc)

    @app.get("/registry/agents")
    def list_agents() -> list[dict[str, object]]:
        return registry_store.list_agents()

    @app.get("/registry/agents/{agent_id}")
    def get_agent(agent_id: str) -> dict[str, object]:
        try:
            return registry_store.get(agent_id)
        except ProtocolError as exc:
            handle_error(exc)

    @app.get("/registry/search")
    def search_agents(capability: str) -> list[dict[str, object]]:
        return registry_store.search(capability)
