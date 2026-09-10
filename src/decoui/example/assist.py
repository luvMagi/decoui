"""How a form fills itself in: completions, cascading fill, lazy defaults."""
from __future__ import annotations

import logging

from decoui import store, tool, toolset

#: Stands in for the service catalogue a real tool would query.
_SERVICES: dict[str, dict[str, str]] = {
    "web-frontend": {"version": "2.4.1", "owner": "platform", "region": "eu-west-1"},
    "auth-service": {"version": "1.9.0", "owner": "identity", "region": "eu-west-1"},
    "billing-api": {"version": "3.0.2", "owner": "payments", "region": "us-east-1"},
    "search-index": {"version": "0.8.7", "owner": "discovery", "region": "eu-north-1"},
}


@toolset(
    label="Form Assist",
    tags=["assist"],
    description="Autocomplete, cascading fill and lazy defaults. Type in Service.",
)
class AssistTools:
    """How a form fills itself in.

    The pattern to copy is the indirection: ``completions`` / ``cascade`` /
    ``defaults`` are given **method names**, not values. Decorator arguments are
    evaluated at import time, when no instance exists, so anything that depends
    on ``self`` has to be named and bound later.
    """

    def __init__(self) -> None:
        """Declare state, without loading it yet.

        Keeping ``__init__`` trivial means the object always exists: if loading
        fails, decoui reports it in a dialog and this toolset still opens with
        the fallbacks declared here. A toolset whose ``__init__`` raises
        disappears from the sidebar entirely.
        """
        self.preferences: dict = {"env": "staging", "dry_run": True}

    def on_startup(self) -> None:
        """Load persisted state before the window appears.

        decoui calls this once during startup, after every toolset has been
        constructed and before the event loop starts. Whatever lands on ``self``
        is reachable from the callbacks below, because those name a method
        rather than capturing a value.

        Reading the settings table is safe here but would not be in a signature
        default: ``init_db()`` has run by now, and had not at import time.

        Two limits apply, see ``docs/startup-lifecycle.md``: this blocks the
        window from appearing, so keep it quick; and the event loop is not
        running, so no timers and no worker threads.
        """
        stored = store("example").get("deploy_env")
        if stored:
            self.preferences["env"] = stored

    @tool(
        label="Deploy Service",
        description=(
            "Type in 'service' for a filtered popup; picking one fills version, "
            "owner and region. 'env' offers a fixed list."
        ),
        placeholders={"service": "start typing: web, auth, billing…"},
        # A list is a static set of suggestions; a string names a method that is
        # called as the user types, on a worker thread.
        completions={
            "env": ["production", "staging", "development"],
            "service": "search_services",
        },
        cascade={"service": "describe_service"},
        defaults="load_defaults",
    )
    def deploy(
        self,
        service: str = "",
        env: str = "",
        version: str = "",
        owner: str = "",
        region: str = "",
        dry_run: bool = True,
    ) -> str:
        """Pretend to deploy a service.

        Args:
            service: Service name. Choosing one fills the three fields below.
            env: Target environment.
            version: Filled in for you.
            owner: Filled in for you.
            region: Filled in for you.
            dry_run: On by default, so the destructive path is opt-in.

        Returns:
            A one-line summary of what would have been deployed.
        """
        logging.info("Deploying %s %s to %s (%s)", service, version, env, region)
        if dry_run:
            logging.warning("dry_run is on -- nothing was actually deployed.")
        # store() is the public way to persist a preference. It namespaces the
        # key, so nothing here can reach decoui's own settings. on_startup()
        # reads it back on the next launch.
        store("example")["deploy_env"] = env
        return f"{service} {version} -> {env}"

    def search_services(self, text: str) -> list[str]:
        """Return catalogue entries matching the typed text.

        Args:
            text: Whatever the user has typed so far.

        Returns:
            Matching service names, or the whole catalogue when nothing is typed.
        """
        if not text:
            return list(_SERVICES)
        needle = text.casefold()
        return [name for name in _SERVICES if needle in name.casefold()]

    def describe_service(self, value: str, form: dict) -> dict:
        """Derive the metadata fields for the chosen service.

        Args:
            value: The committed service name.
            form: Snapshot of the current form values.

        Returns:
            Values for the version, owner and region fields.
        """
        meta = _SERVICES.get(value)
        if meta is None:
            return {"version": "", "owner": "", "region": ""}
        return dict(meta)

    def load_defaults(self) -> dict:
        """Seed the form from state loaded during startup.

        Returns:
            Initial values for the form.
        """
        return dict(self.preferences)
