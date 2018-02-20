"""Common framework for various pytest modules

Usage:

    from .kill_elementsd_before_each_function import *

"""
import logging
import subprocess
import time


def kill_all_elementd():
    result = subprocess.run(['pkill', 'elementsd'])
    if 0 == result.returncode:
        logging.info('killed preexisting elementsd')
        logging.info(f'pause after killing elementsd...')
        time.sleep(2)
    elif 1 == result.returncode:
        # No processes were matched. OK.
        pass
    else:
        msg = f'pkill failed with {result.returncode}; see `man pkill`'
        raise AssertionError(msg)


def setup_function(function):
    kill_all_elementd()
