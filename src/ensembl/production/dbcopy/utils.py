import logging


logger = logging.getLogger(__name__)


def get_filters(values):
    named_filters = {v.replace('%', '.*') for v in values if v}.difference({''})
    logger.debug("from %s", values)
    logger.debug("filters %s", named_filters)
    return named_filters
