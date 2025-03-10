# scanner.py
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class StockScanner:
    def __init__(self, kite):
        self.kite = kite
        self.instruments = None
        self.load_instruments()
    
    def load_instruments(self):
        """Load all NSE equity instruments"""
        try:
            self.instruments = self.kite.instruments("NSE")
            # Filter for only equity instruments
            self.instruments = [i for i in self.instruments if i['segment'] == 'NSE' and i['instrument_type'] == 'EQ']
            logger.info(f"Loaded {len(self.instruments)} equity instruments")
        except Exception as e:
            logger.error(f"Error loading instruments: {e}")
            raise
    
    def get_historical_data(self, instrument_token, days=130):
        """Get historical data for a given instrument token"""
        try:
            to_date = datetime.now().date()
            from_date = to_date - timedelta(days=days)
            
            data = self.kite.historical_data(
                instrument_token=instrument_token,
                from_date=from_date,
                to_date=to_date,
                interval="day"
            )
            
            df = pd.DataFrame(data)
            if df.empty:
                return None
            
            return df
        except Exception as e:
            logger.error(f"Error fetching historical data for {instrument_token}: {e}")
            return None
    
    def calculate_indicators(self, df):
        """Calculate technical indicators on a dataframe"""
        if df is None or df.empty or len(df) < 125:
            return None
        
        try:
            # Calculate highest high and lowest low of last 125 days
            df['125d_high'] = df['high'].rolling(window=125).max().shift(1)
            df['125d_low'] = df['low'].rolling(window=125).min().shift(1)
            
            # Calculate 125-day SMA of volume
            df['volume_sma_125'] = df['volume'].rolling(window=125).mean()
            
            # Calculate 14-day RSI
            delta = df['close'].diff()
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)
            
            avg_gain = gain.rolling(window=14).mean()
            avg_loss = loss.rolling(window=14).mean()
            
            rs = avg_gain / avg_loss
            df['rsi_14'] = 100 - (100 / (1 + rs))
            
            return df
        except Exception as e:
            logger.error(f"Error calculating indicators: {e}")
            return None
    
    def scan_for_breakouts(self):
        """
        Scan for stocks breaking out to new highs with the following conditions:
        1. Closing price > highest price of last 125 days
        2. Today's volume > 125-day SMA of volume
        3. 14-day RSI < 70 (not overbought)
        """
        breakout_stocks = []
        
        for instrument in self.instruments:
            try:
                symbol = instrument['tradingsymbol']
                token = instrument['instrument_token']
                
                df = self.get_historical_data(token)
                df = self.calculate_indicators(df)
                
                if df is None or df.empty:
                    continue
                
                # Get the latest row
                latest = df.iloc[-1]
                
                # Check breakout conditions
                if (latest['close'] > latest['125d_high'] and 
                    latest['volume'] > latest['volume_sma_125'] and 
                    latest['rsi_14'] < 70):
                    
                    breakout_stocks.append({
                        'symbol': symbol,
                        'token': token,
                        'close': latest['close'],
                        'volume': latest['volume'],
                        'rsi': latest['rsi_14'],
                        'volume_ratio': latest['volume'] / latest['volume_sma_125']
                    })
                    
                    logger.info(f"Breakout detected: {symbol} - Close: {latest['close']}, RSI: {latest['rsi_14']:.2f}")
            
            except Exception as e:
                logger.error(f"Error scanning {instrument['tradingsymbol']}: {e}")
                continue
        
        # Sort by volume ratio (highest first)
        if breakout_stocks:
            breakout_stocks = sorted(breakout_stocks, key=lambda x: x['volume_ratio'], reverse=True)
        
        logger.info(f"Found {len(breakout_stocks)} breakout candidates")
        return breakout_stocks
    
    def scan_for_breakdowns(self):
        """
        Scan for stocks making new lows with the following conditions:
        1. Closing price < lowest price of last 125 days
        2. Today's volume < 125-day SMA of volume
        3. 14-day RSI > 30 (not oversold)
        """
        breakdown_stocks = []
        
        for instrument in self.instruments:
            try:
                symbol = instrument['tradingsymbol']
                token = instrument['instrument_token']
                
                df = self.get_historical_data(token)
                df = self.calculate_indicators(df)
                
                if df is None or df.empty:
                    continue
                
                # Get the latest row
                latest = df.iloc[-1]
                
                # Check breakdown conditions
                if (latest['close'] < latest['125d_low'] and 
                    latest['volume'] < latest['volume_sma_125'] and 
                    latest['rsi_14'] > 30):
                    
                    breakdown_stocks.append({
                        'symbol': symbol,
                        'token': token,
                        'close': latest['close'],
                        'volume': latest['volume'],
                        'rsi': latest['rsi_14'],
                        'volume_ratio': latest['volume_sma_125'] / latest['volume']
                    })
                    
                    logger.info(f"Breakdown detected: {symbol} - Close: {latest['close']}, RSI: {latest['rsi_14']:.2f}")
            
            except Exception as e:
                logger.error(f"Error scanning {instrument['tradingsymbol']}: {e}")
                continue
        
        # Sort by volume ratio (highest first - means volume is much lower than average)
        if breakdown_stocks:
            breakdown_stocks = sorted(breakdown_stocks, key=lambda x: x['volume_ratio'], reverse=True)
        
        logger.info(f"Found {len(breakdown_stocks)} breakdown candidates")
        return breakdown_stocks
