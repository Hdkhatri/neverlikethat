# --- ENTRY CODE EXECUTION :: START ---
hedge_required = config['HEDGE_TYPE'] != "NH"
result = (None, None, None, None, None)

# 1. Unified Search (Main + Hedge in one go)
for attempt in range(3):
    # This calls our new fast, robust function
    result = get_robust_optimal_option(
        signal="BUY", 
        spot=close, 
        nearest_price=config['NEAREST_LTP'], 
        instruments_df=instruments_df, 
        config=config, 
        user=user, 
        hedge_offset=200 if config['HEDGE_TYPE'] == "H-M200" else 100, 
        hedge_required=hedge_required
    )
    
    if result[0] is not None:
        break
        
    logging.info(f"⚠️{key} | {user['user']} | Search Attempt {attempt+1} failed. Retrying in 2s...")
    time.sleep(2)

# 2. Validation Check
opt_symbol, strike, expiry, ltp, hedge_opt_symbol = result

if opt_symbol is None or (hedge_required and hedge_opt_symbol is None):
    err_msg = f"❌{key} | {user['user']} {SERVER} | No suitable Pair (Main+Hedge) found for BUY signal."
    logging.error(err_msg)
    send_telegram_message(err_msg, user['telegram_chat_id'], user['telegram_token'])
    send_telegram_message_admin(err_msg)
    continue

# 3. Prepare for Execution
# Note: We don't need a separate get_hedge_option call anymore!
temp_trade_symbols = {
    "OptionSymbol": opt_symbol,
    "hedge_option_symbol": hedge_opt_symbol
}

print(f"📤{key} | {user['user']} {SERVER} | Entering Pair: {opt_symbol} + {hedge_opt_symbol}")
logging.info(f"📤 {key} | Entering Entry Sequence for {opt_symbol} with Hedge {hedge_opt_symbol}")

# 4. Robust Entry Execution
# Ensure execute_robust_entry is programmed to buy the hedge_symbol first for margin
qty, avg_price, hedge_avg_price = execute_robust_entry(temp_trade_symbols, config, user)

# 5. Final Validation and Database Save
if not is_valid_trade_data(qty, avg_price, hedge_avg_price, hedge_required=hedge_required):
    err_msg = f"⚠️ {key} | FAILED Entry: Qty or Price is 0. Database NOT updated."
    logging.error(err_msg)
    send_telegram_message_admin(err_msg)
    break 

trade = {
    "Signal": "BUY", "SpotEntry": close, "OptionSymbol": opt_symbol,
    "Strike": strike, "Expiry": expiry,
    "OptionSellPrice": avg_price, "EntryTime": current_time,
    "qty": qty, "interval": config['INTERVAL'], "real_trade": config['REAL_TRADE'],
    "EntryReason":"SIGNAL_GENERATED", "ExpiryType":config['EXPIRY'],
    "Strategy":config['STRATEGY'], "Key":key, "hedge_option_symbol":hedge_opt_symbol,
    "hedge_strike": strike - 200 if config['HEDGE_TYPE'] == "H-M200" else strike - 100, # Simplified
    "hedge_option_buy_price": hedge_avg_price,
    "hedge_qty": qty if hedge_required else 0, 
    "hedge_entry_time": current_time
}

trade = get_clean_trade(trade)
save_open_position(trade, config, user['id'])
position = "BUY"

send_telegram_message(
    f"🟢{key} | {user['user']} {SERVER} | Buy Signal\n"
    f"Main: {opt_symbol} @ ₹{avg_price:.2f}\n"
    f"Hedge: {hedge_opt_symbol} @ ₹{hedge_avg_price:.2f}\n"
    f"Qty: {qty}", 
    user['telegram_chat_id'], user['telegram_token']
)
# --- ENTRY CODE EXECUTION :: END ---
