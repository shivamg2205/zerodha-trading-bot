# config.py
import os
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class Config:
    def __init__(self, config_path='config.json'):
        self.config_path = config_path
        self.default_config = {
            # API configuration
            'api': {
                'api_key': '',
                'api_secret': '',
                'access_token': ''
            },
            # Breakout strategy parameters
            'breakout_strategy': {
                'lookback_days': 125,
                'volume_ratio_threshold': 1.0,
                'rsi_threshold': 70,
                'position_size_pct': 0.1,
                'take_profit_pct': 3.0,
                'stop_loss_pct': 3.0
            },
            # Breakdown strategy parameters
            'breakdown_strategy': {
                'lookback_days': 125,
                'volume_ratio_threshold': 1.0,
                'rsi_threshold': 30,
                'position_size_pct': 1.0,
                'take_profit_pct': 3.0,
                'stop_loss_pct': 3.0
            },
            # General settings
            'general': {
                'max_positions': 10,
                'scan_interval_minutes': 5,
                'enable_email_notifications': False,
                'auto_close_at_market_close': True
            },
            # Email notification settings
            'notifications': {
                'email': '',
                'smtp_server': '',
                'smtp_port': 587,
                'smtp_username': '',
                'smtp_password': ''
            }
        }
        self.config = self.load_config()
    
    def load_config(self):
        """Load config from file or create default if not exists"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
                    logger.info(f"Configuration loaded from {self.config_path}")
                    return config
            else:
                logger.info(f"No configuration file found at {self.config_path}. Creating default.")
                self.save_config(self.default_config)
                return self.default_config
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            return self.default_config
    
    def save_config(self, config=None):
        """Save config to file"""
        try:
            if config is None:
                config = self.config
            
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=4)
            
            logger.info(f"Configuration saved to {self.config_path}")
            return True
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
            return False
    
    def update_config(self, section, key, value):
        """Update a specific config value"""
        try:
            if section in self.config and key in self.config[section]:
                self.config[section][key] = value
                self.save_config()
                logger.info(f"Updated config: {section}.{key} = {value}")
                return True
            else:
                logger.error(f"Invalid config path: {section}.{key}")
                return False
        except Exception as e:
            logger.error(f"Error updating configuration: {e}")
            return False
    
    def get_value(self, section, key, default=None):
        """Get a specific config value"""
        try:
            if section in self.config and key in self.config[section]:
                return self.config[section][key]
            else:
                return default
        except Exception as e:
            logger.error(f"Error getting configuration value: {e}")
            return default
    
    def get_section(self, section):
        """Get an entire config section"""
        try:
            if section in self.config:
                return self.config[section]
            else:
                return {}
        except Exception as e:
            logger.error(f"Error getting configuration section: {e}")
            return {}
