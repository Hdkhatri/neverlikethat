# --- REENTRY / ROLLOVER LOGIC ---

result = (None, None, None, None, None)
signal = trade["Signal"]
h_offset = 200 if config['HEDGE_TYPE'] == "H-M200" else 100

# -------------------------------
# MAIN + HEDGE SEARCH (ROBUST)
# -------------------------------
for attempt in range(3):
    result = get_robust_optimal_option(
        signal,
        close,
        config['NEAREST_LTP'],
        instruments_df,
        config,
        user,
        hedge_offset=h_offset,
        hedge_required=(config['HEDGE_TYPE'] != "NH")
    )

    if result and result[0] is not None:
        break

    logging.info(f"⚠️{key} | Search Attempt {attempt+1} failed. Retrying in 2s...")
    time.sleep(2)

last_expiry = trade['Expiry']

if not result or result[0] is None:
    logging.error(f"❌ {key} | No expiry found after {last_expiry} for reentry.")
    position = None
    continue

# ✅ NEW unpack (includes hedge)
opt_symbol, strike, expiry, ltp, hedge_opt_symbol = result
main_ltp = ltp

# -------------------------------
# EXPIRY + QTY LOGIC
# -------------------------------
expiry_match = "SAME" if expiry == last_expiry else "DIFF"

target_qty = int(config['QTY'])
existing_qty = int(trade.get('qty', target_qty))
qty_changed = (target_qty != existing_qty)

# -------------------------------
# EXISTING HEDGE DATA
# -------------------------------
old_trade = trade.copy()

hedge_strike = old_trade.get('hedge_strike')
hedge_ltp = get_quotes_with_retry(old_trade.get('hedge_option_symbol'), user) if old_trade.get('hedge_option_symbol') else 0

# -------------------------------
# EXIT
# -------------------------------
exit_qty, exit_avg, exit_h_avg = execute_robust_exit(
    trade,
    config,
    user,
    expiry_match=expiry_match
)

if expiry_match == "SAME" and not qty_changed and hedge_ltp > 0:
    exit_h_avg = hedge_ltp

if not (exit_qty > 0 and exit_avg > 0 and exit_h_avg > 0):
    logging.error("Exit failed")
    position = None
    continue

# -------------------------------
# UPDATE TRADE
# -------------------------------
trade.update({
    "OptionBuyPrice": exit_avg,
    "SpotExit": close,
    "ExitTime": current_time,
    "PnL": (trade["OptionSellPrice"] - exit_avg),
    "qty": exit_qty,
    "ExitReason": "TARGET_HIT",

    "hedge_option_sell_price": exit_h_avg,
    "hedge_exit_time": current_time,
    "hedge_pnl": (exit_h_avg - trade["hedge_option_buy_price"]) if exit_h_avg > 0 else 0,

    "total_pnl": (trade["OptionSellPrice"] - exit_avg) +
                 ((exit_h_avg - trade["hedge_option_buy_price"]) if exit_h_avg > 0 else 0)
})

# -------------------------------
# DB
# -------------------------------
trade = get_clean_trade(trade)
record_trade(trade, config, user['id'])
delete_open_position(trade["OptionSymbol"], config, trade, user['id'])

# -------------------------------
# HEDGE HANDLING (SIMPLIFIED)
# -------------------------------

# SAME expiry + SEMI → reuse old hedge
if config['HEDGE_ROLLOVER_TYPE'] == 'SEMI' and expiry_match == "SAME" and not qty_changed:
    hedge_opt_symbol = old_trade.get('hedge_option_symbol')

# DIFF expiry → must have hedge from robust
elif config['HEDGE_TYPE'] != "NH" and hedge_opt_symbol is None:
    logging.error(f"❌ {key} | No hedge found for new expiry")
    position = None
    continue

# -------------------------------
# ENTRY
# -------------------------------
temp_trade_symbols = {
    "OptionSymbol": opt_symbol,
    "hedge_option_symbol": hedge_opt_symbol
}

skip_h_entry = (
    config['HEDGE_TYPE'] == "NH" or
    (config['HEDGE_ROLLOVER_TYPE'] == 'SEMI' and expiry_match == "SAME" and not qty_changed)
)

new_qty, new_avg, new_h_avg = execute_robust_entry(
    temp_trade_symbols,
    config,
    user,
    skip_hedge_override=skip_h_entry
)

if not is_valid_trade_data(
    new_qty,
    new_avg,
    new_h_avg,
    hedge_required=(config['HEDGE_TYPE'] != "NH")
):
    logging.error("Entry failed")
    position = None
    continue

# -------------------------------
# FINAL TRADE
# -------------------------------
trade = {
    "Signal": signal,
    "SpotEntry": close,
    "OptionSymbol": opt_symbol,
    "Strike": strike,
    "Expiry": expiry,

    "OptionSellPrice": new_avg,
    "EntryTime": current_time,
    "qty": new_qty,

    "interval": config['INTERVAL'],
    "real_trade": config['REAL_TRADE'],
    "EntryReason": "ROLLOVER_REENTRY",
    "Key": key,

    "hedge_option_symbol": hedge_opt_symbol,
    "hedge_strike": hedge_strike,

    "hedge_option_buy_price":
        old_trade.get('hedge_option_sell_price')
        if skip_h_entry and config['HEDGE_TYPE'] != "NH"
        else new_h_avg,

    "hedge_qty": new_qty if config['HEDGE_TYPE'] != "NH" else 0,

    "hedge_entry_time":
        old_trade.get('hedge_entry_time')
        if skip_h_entry else current_time
}

trade = get_clean_trade(trade)
save_open_position(trade, config, user['id'])

logging.info(f"✅ {key} | Rollover/Reentry Complete")
