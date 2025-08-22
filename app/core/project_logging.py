import logging
import logging.config


LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
    'std': {
    'format': '%(asctime)s %(levelname)s %(name)s: %(message)s'
        }
    },
    'handlers': {
        'console': {
        'class': 'logging.StreamHandler',
        'formatter': 'std',
        }
    },
    'root': {
        'level': 'INFO',
        'handlers': ['console']
    }
}


def setup_project_logging():
    logging.config.dictConfig(LOGGING)