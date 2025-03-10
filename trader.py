# trader.py
import logging
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)

class Trader:
    def __init__(self, kite, db):
        self.kite = kite
        self.db = db
    
    def execute_trade(self, symbol, trade_type, quantity, price, take_profit_pct, stop_loss_pct):
        """
        Execute a trade and save it to the database
        
        Parameters:
        symbol (str): Trading symbol
        trade_type (str): "BUY" or "SELL"
        quantity (int): Number of shares to trade
        price (float): Current price
        take_profit_pct (float): Take profit percentage
        stop_loss_pct (float): Stop loss percentage
        """
        try:
            # Calculate take profit and stop loss prices
            if trade_type == "BUY":
                take_profit_price = price * (1 + take_profit_pct / 100)
                stop_loss_price = price * (1 - stop_loss_pct / 100)
            else:  # SELL
                take_profit_price = price * (1 - take_profit_pct / 100)
                stop_loss_price = price * (1 + stop_loss_pct / 100)
            
            # Generate unique order ID
            order_id = str(uuid.uuid4())
            
            # Place order with Zerodha
            try:
                kite_order = self.kite.place_order(
                    variety=self.kite.VARIETY_REGULAR,
                    exchange=self.kite.EXCHANGE_NSE,
                    tradingsymbol=symbol,
                    transaction_type=trade_type,
                    quantity=quantity,
                    product=self.kite.PRODUCT_MIS,  # Intraday
                    order_type=self.kite.ORDER_TYPE_MARKET,
                    price=None,  # Market order
                    validity=self.kite.VALIDITY_DAY
                )
                
                logger.info(f"Order placed successfully. Order ID: {kite_order}")
                
                # Save trade info to database
                self.db.insert_trade(
                    order_id=order_id,
                    kite_order_id=kite_order,
                    symbol=symbol,
                    trade_type=trade_type,
                    quantity=quantity,
                    entry_price=price,
                    take_profit_price=take_profit_price,
                    stop_loss_price=stop_loss_price,
                    status="OPEN",
                    entry_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )
                
                return True
            
            except Exception as e:
                logger.error(f"Error placing order: {e}")
                return False
        
        except Exception as e:
            logger.error(f"Error in execute_trade: {e}")
            return False
    
    def exit_trade(self, trade_id, exit_reason):
        """
        Exit a trade
        
        Parameters:
        trade_id (str): Trade ID
        exit_reason (str): Reason for exiting (TARGET, STOPLOSS, MANUAL)
        """
        try:
            # Get trade info from database
            trade = self.db.get_trade(trade_id)
            
            if not trade:
                logger.error(f"Trade {trade_id} not found")
                return False
            
            if trade['status'] != "OPEN":
                logger.warning(f"Trade {trade_id} is already {trade['status']}")
                return False
            
            # Determine exit transaction type (opposite of entry)
            exit_type = "SELL" if trade['trade_type'] == "BUY" else "BUY"
            
            # Place exit order
            try:
                kite_order = self.kite.place_order(
                    variety=self.kite.VARIETY_REGULAR,
                    exchange=self.kite.EXCHANGE_NSE,
                    tradingsymbol=trade['symbol'],
                    transaction_type=exit_type,
                    quantity=trade['quantity'],
                    product=self.kite.PRODUCT_MIS,  # Intraday
                    order_type=self.kite.ORDER_TYPE_MARKET,
                    price=None,  # Market order
                    validity=self.kite.VALIDITY_DAY
                )
                
                logger.info(f"Exit order placed successfully. Order ID: {kite_order}")
                
                # Get the current price for calculating P&L
                ltp = self.kite.ltp(f"NSE:{trade['symbol']}")
                current_price = ltp[f"NSE:{trade['symbol']}"]["last_price"]
                
                # Calculate P&L
                if trade['trade_type'] == "BUY":
                    pnl = (current_price - trade['entry_price']) * trade['quantity']
                else:  # SELL
                    pnl = (trade['entry_price'] - current_price) * trade['quantity']
                
                # Update trade in database
                self.db.update_trade(
                    trade_id=trade_id,
                    exit_price=current_price,
                    exit_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    exit_reason=exit_reason,
                    pnl=pnl,
                    status="CLOSED"
                )
                
                return True
            
            except Exception as e:
                logger.error(f"Error placing exit order: {e}")
                return False
        
        except Exception as e:
            logger.error(f"Error in exit_trade: {e}")
            return False
    
    def check_exit_conditions(self):
        """Check if any open trades have hit their take profit or stop loss"""
        try:
            # Get all open trades
            open_trades = self.db.get_open_trades()
            
            if not open_trades:
                return
            
            # Get current prices
            symbols = [f"NSE:{trade['symbol']}" for trade in open_trades]
            ltp_data = self.kite.ltp(symbols)
            
            for trade in open_trades:
                symbol_key = f"NSE:{trade['symbol']}"
                
                if symbol_key not in ltp_data:
                    logger.warning(f"No price data for {symbol_key}")
                    continue
                
                current_price = ltp_data[symbol_key]["last_price"]
                
                # Check for take profit or stop loss hit
                if trade['trade_type'] == "BUY":
                    if current_price >= trade['take_profit_price']:
                        logger.info(f"Take profit hit for {trade['symbol']} at {current_price}")
                        self.exit_trade(trade['id'], "TARGET")
                    
                    elif current_price <= trade['stop_loss_price']:
                        logger.info(f"Stop loss hit for {trade['symbol']} at {current_price}")
                        self.exit_trade(trade['id'], "STOPLOSS")
                
                else:  # SELL
                    if current_price <= trade['take_profit_price']:
                        logger.info(f"Take profit hit for {trade['symbol']} at {current_price}")
                        self.exit_trade(trade['id'], "TARGET")
                    
                    elif current_price >= trade['stop_loss_price']:
                        logger.info(f"Stop loss hit for {trade['symbol']} at {current_price}")
                        self.exit_trade(trade['id'], "STOPLOSS")
        
        except Exception as e:
            logger.error(f"Error in check_exit_conditions: {e}")
