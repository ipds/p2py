import logging, colorlog, os, errno

#log
LOG_DIR = 'p2py-logs/'

def init_logger(dunder_name, testing_mode, address, mute=False) -> logging.Logger:
    log_format = (
        f'{address} - '
        '%(name)s - '
        '%(funcName)s - '
        '%(levelname)s - '
        '%(message)s'
    )
    bold_seq = '\033[1m'
    colorlog_format = (
        f'{bold_seq} '
        '%(log_color)s '
        f'{log_format}'
    )
    colorlog.basicConfig(format=colorlog_format)
    logger = logging.getLogger(dunder_name)

    logger.propagate = not mute

    if testing_mode:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    try:
        crate_log_files()
    except:
        pass

    # Output full log
    fh = logging.FileHandler(LOG_DIR+'app.log')
    fh.setLevel(logging.DEBUG)
    formatter = logging.Formatter(log_format)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    # Output warning log
    fh = logging.FileHandler(LOG_DIR+'app.warning.log')
    fh.setLevel(logging.WARNING)
    formatter = logging.Formatter(log_format)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    # Output error log
    fh = logging.FileHandler(LOG_DIR+'app.error.log')
    fh.setLevel(logging.ERROR)
    formatter = logging.Formatter(log_format)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    return logger
    
def crate_log_files():
    if not os.path.exists(os.path.dirname(LOG_DIR)):
        try:
            os.makedirs(os.path.dirname(LOG_DIR))
        except OSError as exc: # Guard against race condition
            if exc.errno != errno.EEXIST:
                raise