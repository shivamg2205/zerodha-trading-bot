# main.py
import os
import time
import logging
import threading
from datetime import datetime, time as datetime_time
import pandas as pd
import streamlit as st
from apscheduler.schedulers.background import BackgroundScheduler
from kiteconnect import KiteConnect

from scanner import StockScanner
from trader import Trader
from database import Database

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("trading_app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class TradingApp:
    def __init__(self, api_key, api_secret, access_token=None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.access_token = access_token
        self.kite = None
        self.scanner = None
        self.trader = None
        self.db = Database('trades.db')
        self.scheduler = BackgroundScheduler()
        self.is_market_open = False
        self.initialize_kite()
        
    def initialize_kite(self):
        """Initialize Kite Connect API"""
        self.kite = KiteConnect(api_key=self.api_key)
        
        if not self.access_token:
            # Generate a request token URL
            print(f"Please visit this URL to get the request token: {self.kite.login_url()}")
            request_token = input("Enter the request token: ")
            
            try:
                # Generate access token
                data = self.kite.generate_session(request_token, api_secret=self.api_secret)
                self.access_token = data["access_token"]
                print(f"Access token: {self.access_token}")
            except Exception as e:
                logger.error(f"Error generating session: {e}")
                raise
        
        # Set access token
        self.kite.set_access_token(self.access_token)
        
        # Initialize scanner and trader
        self.scanner = StockScanner(self.kite)
        self.trader = Trader(self.kite, self.db)
        
        logger.info("Kite Connect API initialized successfully")
    
    def check_market_status(self):
        """Check if the market is open"""
        now = datetime.now().time()
        market_open = datetime_time(9, 15)
        market_close = datetime_time(15, 30)
        
        if market_open <= now <= market_close and datetime.now().weekday() < 5:
            if not self.is_market_open:
                logger.info("Market is open")
                self.is_market_open = True
            return True
        else:
            if self.is_market_open:
                logger.info("Market is closed")
                self.is_market_open = False
            return False
    
    def scan_and_trade(self):
        """Main function to scan stocks and execute trades"""
        if not self.check_market_status():
            logger.info("Market is closed. Skipping scan.")
            return
        
        try:
            # Get available funds and open positions
            profile = self.kite.profile()
            margins = self.kite.margins()
            available_cash = margins["equity"]["available"]["cash"]
            positions = self.kite.positions()["net"]
            
            # Count open positions
            open_positions_count = len([p for p in positions if p["quantity"] != 0])
            
            logger.info(f"Available cash: {available_cash}")
            logger.info(f"Open positions: {open_positions_count}")
            
            # Only proceed if we have less than 10 open positions
            if open_positions_count >= 10:
                logger.info("Maximum positions (10) reached. Not taking new trades.")
                return
            
            # Scan for breakout stocks
            logger.info("Scanning for breakout opportunities...")
            breakout_stocks = self.scanner.scan_for_breakouts()
            
            # Scan for breakdown stocks
            logger.info("Scanning for breakdown opportunities...")
            breakdown_stocks = self.scanner.scan_for_breakdowns()
            
            # Execute trades based on scanner results
            if breakout_stocks and open_positions_count < 10:
                # Calculate position size (0.1% of available funds)
                position_size = available_cash * 0.001
                
                for stock in breakout_stocks:
                    if open_positions_count >= 10:
                        break
                    
                    logger.info(f"Executing BUY trade for {stock['symbol']}")
                    self.trader.execute_trade(
                        symbol=stock['symbol'],
                        trade_type="BUY",
                        quantity=int(position_size / stock['close']),
                        price=stock['close'],
                        take_profit_pct=3.0,
                        stop_loss_pct=3.0
                    )
                    open_positions_count += 1
            
            if breakdown_stocks and open_positions_count < 10:
                # Calculate position size (1% of available funds)
                position_size = available_cash * 0.01
                
                for stock in breakdown_stocks:
                    if open_positions_count >= 10:
                        break
                    
                    logger.info(f"Executing SELL trade for {stock['symbol']}")
                    self.trader.execute_trade(
                        symbol=stock['symbol'],
                        trade_type="SELL",
                        quantity=int(position_size / stock['close']),
                        price=stock['close'],
                        take_profit_pct=3.0,
                        stop_loss_pct=3.0
                    )
                    open_positions_count += 1
            
            # Check for target/stoploss hits
            self.trader.check_exit_conditions()
            
        except Exception as e:
            logger.error(f"Error in scan_and_trade: {e}")
    
    def start(self):
        """Start the trading app"""
        logger.info("Starting trading application")
        
        # Schedule the scan to run every 5 minutes
        self.scheduler.add_job(self.scan_and_trade, 'interval', minutes=5)
        self.scheduler.start()
        
        try:
            # Run the Streamlit dashboard in a separate thread
            dashboard_thread = threading.Thread(target=self.run_dashboard)
            dashboard_thread.daemon = True
            dashboard_thread.start()
            
            # Keep the main thread alive
            while True:
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            self.stop()
    
    def run_dashboard(self):
        """Run the Streamlit dashboard"""
        os.system("streamlit run dashboard.py")
    
    def stop(self):
        """Stop the trading app"""
        logger.info("Stopping trading application")
        self.scheduler.shutdown()


# Usage example
if __name__ == "__main__":
    # Load API credentials
    API_KEY = "your_api_key"
    API_SECRET = "your_api_secret"
    ACCESS_TOKEN = None  # If you already have an access token
    
    app = TradingApp(API_KEY, API_SECRET, ACCESS_TOKEN)
    app.start()
