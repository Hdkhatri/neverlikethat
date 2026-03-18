# ENTRY CODE EXECUTION :: START

result = (None, None, None, None, None)

for attempt in range(3):
    result = get_robust_optimal_option(
        "BUY",
        close,
        config['NEAREST_LTP'],
        instruments_df,
        config,
        user,
        hedge_offset=config.get('HEDGE_OFFSET', 200),
        hedge_required=False   # ✅ EXACT same behavior as before
    )
    
    # If valid symbol found
    if result and result[0] is not None:
        break
        
    logging.info(f"⚠️{key} | {user['user']} {SERVER} | Search Attempt {attempt+1} failed to find an option within tolerance. Retrying in 2s...")
    time.sleep(2)

# -------------------------------
# FAILURE CHECK
# -------------------------------
if not result or result[0] is None:
    logging.error(f"❌{key} | {user['user']} {SERVER} | No suitable option found for BUY signal.")
    continue

# -------------------------------
# UNPACK (ignore hedge output)
# -------------------------------
opt_symbol, strike, expiry, ltp, _ = result

# -------------------------------
# PREPARE ENTRY SYMBOLS (UNCHANGED)
# -------------------------------
temp_trade_symbols = {
    "OptionSymbol": opt_symbol,
    "hedge_option_symbol": config.get('HEDGE_SYMBOL', '-')
}

print(f"📤 {key} | {user['user']} {SERVER} | Enter Signal Generated: Selling {opt_symbol} | LTP: ₹{ltp:.2f}")
logging.info(f"📤 {key} | {user['user']} {SERVER} | Enter Signal Generated: Selling {opt_symbol} | LTP: ₹{ltp:.2f}")

# -------------------------------
# ENTRY EXECUTION
# -------------------------------
new_qty, avg_price, hedge_avg_price = execute_robust_entry(
    temp_trade_symbols,
    config,
    user
)

logging.info(f"📤{key} | Entered without Hedge position {opt_symbol} with Avg price: ₹{avg_price:.2f} | Qty: {new_qty}.")

# -------------------------------
# VALIDATION (UNCHANGED)
# -------------------------------
if not is_valid_trade_data(new_qty, avg_price, hedge_avg_price, hedge_required=False):
    err_msg = f"⚠️ {key} | FAILED ENTRY: Qty ({new_qty}) or Price ({avg_price}) is 0. Database NOT updated."
    logging.error(err_msg)
    send_telegram_message_admin(err_msg)
    break

# -------------------------------
# SAVE TRADE
# -------------------------------
trade = {
    "Signal": "BUY",
    "SpotEntry": close,
    "OptionSymbol": opt_symbol,
    "Strike": strike,
    "Expiry": expiry,

    "OptionSellPrice": avg_price,
    "EntryTime": current_time,
    "qty": new_qty,

    "interval": config['INTERVAL'],
    "real_trade": config['REAL_TRADE'],
    "EntryReason": "SIGNAL_GENERATED",
    "ExpiryType": config['EXPIRY'],
    "Strategy": config['STRATEGY'],
    "Key": key,

    "hedge_option_symbol": temp_trade_symbols["hedge_option_symbol"],
    "hedge_strike": "-",
    "hedge_option_buy_price": hedge_avg_price,
    "hedge_qty": new_qty if hedge_avg_price > 0 else "-",
    "hedge_entry_time": current_time if hedge_avg_price > 0 else "-"
}

trade = get_clean_trade(trade)
save_open_position(trade, config, user['id'])

position = "BUY"

send_telegram_message(
    f"🟢{key} | BUY Entry Signal Generated\n Selling {opt_symbol} | Avg ₹{avg_price:.2f} | Qty: {new_qty}",
    user['telegram_chat_id'],
    user['telegram_token']
)

# ENTRY CODE EXECUTION :: END
