from workers.tasks.system.ping import run as run_ping
from workers.tasks.system.purge_old_articles import run as run_purge_old_articles

__all__ = ["run_ping", "run_purge_old_articles"]
