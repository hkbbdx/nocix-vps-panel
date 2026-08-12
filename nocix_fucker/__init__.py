__version__ = "0.0.4"
__license__ = "MIT"

from dotenv import load_dotenv

load_dotenv()

from nocix_fucker.client import Client
from nocix_fucker.config import Config
