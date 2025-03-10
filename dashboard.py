# dashboard.py
import os
import time
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta

from kiteconnect import KiteConnect
from database import Database

# Initialize Zerodha API with environment variables
API_KEY = os.environ.get("ZERODHA_API_KEY", "your_api_key")
API_SECRET = os.environ.get("ZERODHA_API_SECRET", "your_api_secret")
ACCESS_TOKEN = os.environ.get("ZERODHA_ACCESS_TOKEN")

# Initialize database
db = Database('trades.db')

# Initialize Kite Connect if access token is available
kite = None
if ACCESS_TOKEN:
    kite = KiteConnect(api_key=API_KEY)
    kite.set_access_token(ACCESS_TOKEN)

# Page configuration
st.set_page_config(
    page_title="Zerodha Trading Bot",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Sidebar
st.sidebar.title("Zerodha Trading Bot")
st.sidebar.image("https://zerodha.com/static/images/logo.svg", width=200)

# Sidebar navigation
page = st.sidebar.radio("Navigation", ["Dashboard", "Active Trades", "Trade History", "Settings"])

# Authentication section in sidebar
with st.sidebar.expander("Authentication", expanded=not ACCESS_TOKEN):
    if not ACCESS_TOKEN:
        st.warning("Not authenticated with Zerodha")
        
        # Input fields for API credentials
        api_key_input = st.text_input("API Key", value=API_KEY)
        api_secret_input = st.text_input("API Secret", value=API_SECRET, type="password")
        
        if st.button("Generate Login URL"):
            try:
                temp_kite = KiteConnect(api_key=api_key_input)
                login_url = temp_kite.login_url()
                st.markdown(f"[Click here to login]({login_url})")
            except Exception as e:
                st.error(f"Error generating login URL: {e}")
        
        request_token = st.text_input("Request Token")
        
        if st.button("Generate Access Token") and request_token:
            try:
                temp_kite = KiteConnect(api_key=api_key_input)
                data = temp_kite.generate_session(request_token, api_secret=api_secret_input)
                access_token = data["access_token"]
                st.success(f"Access token generated: {access_token}")
                st.info("Set this as ZERODHA_ACCESS_TOKEN environment variable")
                
                # Automatically set for current session
                ACCESS_TOKEN = access_token
                kite = temp_kite
            except Exception as e:
                st.error(f"Error generating access token: {e}")
    else:
        st.success("Authenticated with Zerodha")

# Function to fetch account details
def get_account_details():
    if not kite:
        return {
            "user_id": "Not authenticated",
            "user_name": "Not authenticated",
            "available_cash": 0,
            "used_margin": 0,
            "open_positions": 0
        }
    
    try:
        profile = kite.profile()
        margins = kite.margins()
        positions = kite.positions()
        
        open_positions = len([p for p in positions.get("net", []) if p["quantity"] != 0])
        
        return {
            "user_id": profile["user_id"],
            "user_name": profile["user_name"],
            "available_cash": margins["equity"]["available"]["cash"],
            "used_margin": margins["equity"]["utilised"]["debits"],
            "open_positions": open_positions
        }
    except Exception as e:
        st.error(f"Error fetching account details: {e}")
        return {
            "user_id": "Error",
            "user_name": "Error",
            "available_cash": 0,
            "used_margin": 0,
            "open_positions": 0
        }

# Function to exit a trade
def exit_trade(trade_id):
    if not kite:
        st.error("Not authenticated with Zerodha")
        return False
    
    try:
        # Get trade info
        trade = db.get_trade(trade_id)
        
        if not trade:
            st.error(f"Trade {trade_id} not found")
            return False
        
        # Determine exit transaction type (opposite of entry)
        exit_type = "SELL" if trade['trade_type'] == "BUY" else "BUY"
        
        # Place exit order
        kite_order = kite.place_order(
            variety=kite.VARIETY_REGULAR,
            exchange=kite.EXCHANGE_NSE,
            tradingsymbol=trade['symbol'],
            transaction_type=exit_type,
            quantity=trade['quantity'],
            product=kite.PRODUCT_MIS,
            order_type=kite.ORDER_TYPE_MARKET,
            price=None
        )
        
        # Get current price
        ltp = kite.ltp(f"NSE:{trade['symbol']}")
        current_price = ltp[f"NSE:{trade['symbol']}"]["last_price"]
        
        # Calculate P&L
        if trade['trade_type'] == "BUY":
            pnl = (current_price - trade['entry_price']) * trade['quantity']
        else:
            pnl = (trade['entry_price'] - current_price) * trade['quantity']
        
        # Update trade in database
        db.update_trade(
            trade_id=trade_id,
            exit_price=current_price,
            exit_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            exit_reason="MANUAL",
            pnl=pnl,
            status="CLOSED"
        )
        
        return True
    
    except Exception as e:
        st.error(f"Error exiting trade: {e}")
        return False

# Dashboard page
if page == "Dashboard":
    st.title("Trading Dashboard")
    
    # Fetch account details
    account = get_account_details()
    
    # Account overview
    col1, col2, col3 = st.columns(3)
    col1.metric("Available Cash", f"₹{account['available_cash']:,.2f}")
    col2.metric("Used Margin", f"₹{account['used_margin']:,.2f}")
    col3.metric("Open Positions", account['open_positions'])
    
    # Fetch daily summaries
    daily_summaries = db.get_daily_summaries(days=30)
    
    if daily_summaries:
        st.subheader("Performance Summary (Last 30 Days)")
        
        # Convert to DataFrame
        df_summary = pd.DataFrame(daily_summaries)
        df_summary['win_rate'] = (df_summary['winning_trades'] / df_summary['total_trades'] * 100).round(2)
        
        # Create metrics
        total_pnl = df_summary['total_pnl'].sum()
        win_rate = (df_summary['winning_trades'].sum() / df_summary['total_trades'].sum() * 100) if df_summary['total_trades'].sum() > 0 else 0
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total P&L", f"₹{total_pnl:,.2f}", delta=f"{'+' if total_pnl > 0 else ''}{total_pnl:,.2f}")
        col2.metric("Win Rate", f"{win_rate:.2f}%")
        col3.metric("Total Trades", df_summary['total_trades'].sum())
        
        # P&L chart
        st.subheader("Daily P&L")
        fig_pnl = px.bar(
            df_summary,
            x='date',
            y='total_pnl',
            color=df_summary['total_pnl'] > 0,
            color_discrete_map={True: 'green', False: 'red'},
            labels={'date': 'Date', 'total_pnl': 'P&L (₹)'},
            title="Daily Profit/Loss"
        )
        st.plotly_chart(fig_pnl, use_container_width=True)
        
        # Win rate chart
        st.subheader("Daily Win Rate")
        fig_win_rate = px.line(
            df_summary,
            x='date',
            y='win_rate',
            markers=True,
            labels={'date': 'Date', 'win_rate': 'Win Rate (%)'},
            title="Daily Win Rate"
        )
        fig_win_rate.update_layout(yaxis_range=[0, 100])
        st.plotly_chart(fig_win_rate, use_container_width=True)
    else:
        st.info("No trade data available yet. Start trading to see performance metrics.")

# Active Trades page
elif page == "Active Trades":
    st.title("Active Trades")
    
    # Fetch open trades
    open_trades = db.get_open_trades()
    
    if open_trades:
        # Convert to DataFrame
        df_trades = pd.DataFrame(open_trades)
        
        # Fetch current prices if authenticated
        if kite:
            symbols = [f"NSE:{trade['symbol']}" for trade in open_trades]
            try:
                ltp_data = kite.ltp(symbols)
                
                # Add current price and unrealized P&L
                current_prices = []
                unrealized_pnl = []
                
                for trade in open_trades:
                    symbol_key = f"NSE:{trade['symbol']}"
                    if symbol_key in ltp_data:
                        current_price = ltp_data[symbol_key]["last_price"]
                        
                        if trade['trade_type'] == "BUY":
                            pnl = (current_price - trade['entry_price']) * trade['quantity']
                        else:
                            pnl = (trade['entry_price'] - current_price) * trade['quantity']
                        
                        current_prices.append(current_price)
                        unrealized_pnl.append(pnl)
                    else:
                        current_prices.append(None)
                        unrealized_pnl.append(None)
                
                df_trades['current_price'] = current_prices
                df_trades['unrealized_pnl'] = unrealized_pnl
                
                # Calculate distance to target and stop loss
                distance_to_target = []
                distance_to_sl = []
                
                for i, trade in enumerate(open_trades):
                    if current_prices[i]:
                        if trade['trade_type'] == "BUY":
                            dist_target = ((trade['take_profit_price'] - current_prices[i]) / current_prices[i]) * 100
                            dist_sl = ((current_prices[i] - trade['stop_loss_price']) / current_prices[i]) * 100
                        else:
                            dist_target = ((current_prices[i] - trade['take_profit_price']) / current_prices[i]) * 100
                            dist_sl = ((trade['stop_loss_price'] - current_prices[i]) / current_prices[i]) * 100
                        
                        distance_to_target.append(f"{dist_target:.2f}%")
                        distance_to_sl.append(f"{dist_sl:.2f}%")
                    else:
                        distance_to_target.append(None)
                        distance_to_sl.append(None)
                
                df_trades['distance_to_target'] = distance_to_target
                df_trades['distance_to_sl'] = distance_to_sl
            
            except Exception as e:
                st.error(f"Error fetching current prices: {e}")
        
        # Define display columns
        display_cols = ['symbol', 'trade_type', 'quantity', 'entry_price']
        
        if 'current_price' in df_trades.columns:
            display_cols.extend(['current_price', 'unrealized_pnl', 'distance_to_target', 'distance_to_sl'])
        
        display_cols.extend(['take_profit_price', 'stop_loss_price', 'entry_time'])
        
        # Display trades table with exit buttons
        for i, trade in df_trades.iterrows():
            with st.expander(f"{trade['symbol']} - {trade['trade_type']} - {trade['quantity']} shares"):
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    # Display trade details
                    details = {
                        "Symbol": trade['symbol'],
                        "Type": trade['trade_type'],
                        "Quantity": trade['quantity'],
                        "Entry Price": f"₹{trade['entry_price']:.2f}",
                        "Entry Time": trade['entry_time']
                    }
                    
                    if 'current_price' in df_trades.columns and trade['current_price']:
                        details.update({
                            "Current Price": f"₹{trade['current_price']:.2f}",
                            "Unrealized P&L": f"₹{trade['unrealized_pnl']:.2f}",
                            "Distance to Target": trade['distance_to_target'],
                            "Distance to Stop Loss": trade['distance_to_sl']
                        })
                    
                    details.update({
                        "Take Profit": f"₹{trade['take_profit_price']:.2f}",
                        "Stop Loss": f"₹{trade['stop_loss_price']:.2f}"
                    })
                    
                    for key, value in details.items():
                        st.text(f"{key}: {value}")
                
                with col2:
                    if st.button(f"Exit Trade", key=f"exit_{trade['id']}"):
                        if exit_trade(trade['id']):
                            st.success(f"Trade {trade['symbol']} exited successfully")
                            time.sleep(1)
                            st.experimental_rerun()
                        else:
                            st.error("Failed to exit trade")
    else:
        st.info("No active trades at the moment.")

# Trade History page
elif page == "Trade History":
    st.title("Trade History")
    
    # Pagination
    page_size = 20
    page_number = st.number_input("Page", min_value=1, value=1, step=1)
    offset = (page_number - 1) * page_size
    
    # Fetch trades with pagination
    trades_data = db.get_all_trades(limit=page_size, offset=offset)
    trades = trades_data['trades']
    total_trades = trades_data['total']
    
    # Calculate total pages
    total_pages = (total_trades + page_size - 1) // page_size
    
    st.write(f"Showing page {page_number} of {total_pages} ({total_trades} total trades)")
    
    if trades:
        # Convert to DataFrame
        df_trades = pd.DataFrame(trades)
        
        # Add P&L percentage
        df_trades['pnl_pct'] = None
        for i, trade in df_trades.iterrows():
            if trade['exit_price'] and trade['entry_price']:
                if trade['trade_type'] == "BUY":
                    pnl_pct = (trade['exit_price'] - trade['entry_price']) / trade['entry_price'] * 100
                else:
                    pnl_pct = (trade['entry_price'] - trade['exit_price']) / trade['entry_price'] * 100
                df_trades.at[i, 'pnl_pct'] = pnl_pct
        
        # Format the DataFrame for display
        df_display = df_trades.copy()
        
        # Format numeric columns
        if 'entry_price' in df_display.columns:
            df_display['entry_price'] = df_display['entry_price'].apply(lambda x: f"₹{x:.2f}" if x else None)
        
        if 'exit_price' in df_display.columns:
            df_display['exit_price'] = df_display['exit_price'].apply(lambda x: f"₹{x:.2f}" if x else None)
        
        if 'take_profit_price' in df_display.columns:
            df_display['take_profit_price'] = df_display['take_profit_price'].apply(lambda x: f"₹{x:.2f}" if x else None)
        
        if 'stop_loss_price' in df_display.columns:
            df_display['stop_loss_price'] = df_display['stop_loss_price'].apply(lambda x: f"₹{x:.2f}" if x else None)
        
        if 'pnl' in df_display.columns:
            df_display['pnl'] = df_display['pnl'].apply(lambda x: f"₹{x:.2f}" if x else None)
        
        if 'pnl_pct' in df_display.columns:
            df_display['pnl_pct'] = df_display['pnl_pct'].apply(lambda x: f"{x:.2f}%" if x is not None else None)
        
        # Define display columns
        display_cols = [
            'symbol', 'trade_type', 'quantity', 'entry_price', 'exit_price',
            'pnl', 'pnl_pct', 'entry_time', 'exit_time', 'exit_reason', 'status'
        ]
        
        # Keep only columns that exist in the DataFrame
        display_cols = [col for col in display_cols if col in df_display.columns]
        
        # Display the trades
        st.dataframe(df_display[display_cols], use_container_width=True)
        
        # Pagination navigation
        col1, col2, col3 = st.columns([1, 3, 1])
        
        with col1:
            if page_number > 1:
                if st.button("Previous Page"):
                    st.session_state.page_number = page_number - 1
                    st.experimental_rerun()
        
        with col3:
            if page_number < total_pages:
                if st.button("Next Page"):
                    st.session_state.page_number = page_number + 1
                    st.experimental_rerun()
    else:
        st.info("No trade history available.")

# Settings page
elif page == "Settings":
    st.title("Settings")
    
    with st.expander("Strategy Settings", expanded=True):
        st.subheader("Breakout Strategy")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.number_input("Lookback Period (Days)", min_value=5, max_value=365, value=125, step=1)
            st.number_input("Volume Ratio Threshold", min_value=0.1, max_value=5.0, value=1.0, step=0.1)
            st.number_input("RSI Threshold (Upper)", min_value=50, max_value=90, value=70, step=1)
        
        with col2:
            st.number_input("Position Size (% of Capital)", min_value=0.01, max_value=5.0, value=0.1, step=0.01)
            st.number_input("Take Profit (%)", min_value=0.1, max_value=20.0, value=3.0, step=0.1)
            st.number_input("Stop Loss (%)", min_value=0.1, max_value=20.0, value=3.0, step=0.1)
        
        st.subheader("Breakdown Strategy")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.number_input("Lookback Period (Days) - Breakdown", min_value=5, max_value=365, value=125, step=1)
            st.number_input("Volume Ratio Threshold - Breakdown", min_value=0.1, max_value=5.0, value=1.0, step=0.1)
            st.number_input("RSI Threshold (Lower)", min_value=10, max_value=50, value=30, step=1)
        
        with col2:
            st.number_input("Position Size (% of Capital) - Breakdown", min_value=0.01, max_value=5.0, value=1.0, step=0.01)
            st.number_input("Take Profit (%) - Breakdown", min_value=0.1, max_value=20.0, value=3.0, step=0.1)
            st.number_input("Stop Loss (%) - Breakdown", min_value=0.1, max_value=20.0, value=3.0, step=0.1)
    
    with st.expander("General Settings"):
        st.number_input("Maximum Active Positions", min_value=1, max_value=50, value=10, step=1)
        st.number_input("Scan Interval (Minutes)", min_value=1, max_value=60, value=5, step=1)
        st.checkbox("Enable Email Notifications", value=False)
        st.checkbox("Auto-close All Positions at Market Close", value=True)
    
    if st.button("Save Settings"):
        st.success("Settings saved successfully!")
