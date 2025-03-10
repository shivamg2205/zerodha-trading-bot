# database.py
import sqlite3
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path):
        self.db_path = db_path
        self.init_db()
    
    def get_connection(self):
        """Get a database connection"""
        return sqlite3.connect(self.db_path)
    
    def init_db(self):
        """Initialize the database schema"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Create trades table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id TEXT PRIMARY KEY,
                kite_order_id TEXT,
                symbol TEXT,
                trade_type TEXT,
                quantity INTEGER,
                entry_price REAL,
                exit_price REAL,
                take_profit_price REAL,
                stop_loss_price REAL,
                entry_time TEXT,
                exit_time TEXT,
                exit_reason TEXT,
                pnl REAL,
                status TEXT
            )
            ''')
            
            # Create daily_summary table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_summary (
                date TEXT PRIMARY KEY,
                total_trades INTEGER,
                winning_trades INTEGER,
                losing_trades INTEGER,
                total_pnl REAL
            )
            ''')
            
            conn.commit()
            conn.close()
            
            logger.info("Database initialized successfully")
        
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
            raise
    
    def insert_trade(self, order_id, kite_order_id, symbol, trade_type, quantity, 
                     entry_price, take_profit_price, stop_loss_price, status, entry_time):
        """Insert a new trade into the database"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
            INSERT INTO trades (
                id, kite_order_id, symbol, trade_type, quantity, 
                entry_price, take_profit_price, stop_loss_price, 
                status, entry_time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                order_id, kite_order_id, symbol, trade_type, quantity,
                entry_price, take_profit_price, stop_loss_price,
                status, entry_time
            ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Trade {order_id} inserted successfully")
            return True
        
        except Exception as e:
            logger.error(f"Error inserting trade: {e}")
            return False
    
    def update_trade(self, trade_id, exit_price, exit_time, exit_reason, pnl, status):
        """Update a trade in the database"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
            UPDATE trades
            SET exit_price = ?, exit_time = ?, exit_reason = ?, pnl = ?, status = ?
            WHERE id = ?
            ''', (exit_price, exit_time, exit_reason, pnl, status, trade_id))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Trade {trade_id} updated successfully")
            
            # Update daily summary
            self.update_daily_summary()
            
            return True
        
        except Exception as e:
            logger.error(f"Error updating trade: {e}")
            return False
    
    def get_trade(self, trade_id):
        """Get a trade by ID"""
        try:
            conn = self.get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM trades WHERE id = ?', (trade_id,))
            trade = cursor.fetchone()
            
            conn.close()
            
            if trade:
                return dict(trade)
            else:
                return None
        
        except Exception as e:
            logger.error(f"Error getting trade: {e}")
            return None
    
    def get_open_trades(self):
        """Get all open trades"""
        try:
            conn = self.get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM trades WHERE status = "OPEN"')
            trades = cursor.fetchall()
            
            conn.close()
            
            return [dict(trade) for trade in trades]
        
        except Exception as e:
            logger.error(f"Error getting open trades: {e}")
            return []
    
    def get_all_trades(self, limit=100, offset=0):
        """Get all trades with pagination"""
        try:
            conn = self.get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
            SELECT * FROM trades
            ORDER BY entry_time DESC
            LIMIT ? OFFSET ?
            ''', (limit, offset))
            
            trades = cursor.fetchall()
            
            # Get total count
            cursor.execute('SELECT COUNT(*) FROM trades')
            total = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                'trades': [dict(trade) for trade in trades],
                'total': total
            }
        
        except Exception as e:
            logger.error(f"Error getting all trades: {e}")
            return {'trades': [], 'total': 0}
    
    def update_daily_summary(self):
        """Update the daily summary table"""
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Get today's closed trades
            cursor.execute('''
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning,
                   SUM(CASE WHEN pnl <= 0 THEN 1 ELSE 0 END) as losing,
                   SUM(pnl) as total_pnl
            FROM trades
            WHERE date(exit_time) = ? AND status = "CLOSED"
            ''', (today,))
            
            result = cursor.fetchone()
            
            if result and result[0] > 0:
                total_trades, winning_trades, losing_trades, total_pnl = result
                
                # Check if today's summary exists
                cursor.execute('SELECT 1 FROM daily_summary WHERE date = ?', (today,))
                exists = cursor.fetchone()
                
                if exists:
                    # Update existing summary
                    cursor.execute('''
                    UPDATE daily_summary
                    SET total_trades = ?, winning_trades = ?, losing_trades = ?, total_pnl = ?
                    WHERE date = ?
                    ''', (total_trades, winning_trades, losing_trades, total_pnl, today))
                else:
                    # Insert new summary
                    cursor.execute('''
                    INSERT INTO daily_summary (date, total_trades, winning_trades, losing_trades, total_pnl)
                    VALUES (?, ?, ?, ?, ?)
                    ''', (today, total_trades, winning_trades, losing_trades, total_pnl))
                
                conn.commit()
            
            conn.close()
            
            logger.info(f"Daily summary for {today} updated successfully")
            return True
        
        except Exception as e:
            logger.error(f"Error updating daily summary: {e}")
            return False
    
    def get_daily_summaries(self, days=30):
        """Get daily summaries for the last N days"""
        try:
            conn = self.get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
            SELECT *
            FROM daily_summary
            ORDER BY date DESC
            LIMIT ?
            ''', (days,))
            
            summaries = cursor.fetchall()
            conn.close()
            
            return [dict(summary) for summary in summaries]
        
        except Exception as e:
            logger.error(f"Error getting daily summaries: {e}")
            return []
