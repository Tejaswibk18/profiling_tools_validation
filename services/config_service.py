import configparser


CONFIG_FILE = "config.ini"


def load_config():
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)

    return config