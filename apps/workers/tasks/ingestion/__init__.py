from tasks.ingestion import (
    watch_newsdata,  # noqa: F401  register tasks with Celery
    watch_rss,  # noqa: F401  register tasks with Celery
    watch_twitter,  # noqa: F401  register tasks with Celery
    watch_youtube,  # noqa: F401  register tasks with Celery
)
