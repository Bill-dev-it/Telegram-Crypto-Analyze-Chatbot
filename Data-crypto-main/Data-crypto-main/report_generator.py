from typing import Dict, Any

def generate_telegram_report(
    token_address: str,
    goplus_data: Dict[str, Any],
    dex_data: Dict[str, Any],
    deployer_data: Dict[str, Any],
    holders_data: Dict[str, Any],
    ai_report: str
) -> str:
    """
    Generates a localized (Vietnamese), emoji-rich Telegram report summarizing 
    the Token Scan result, and provides a final investment conclusion.
    """
    
    # 1. Format GoPlus Security Data
    goplus_section = "🛡 **Bảo mật Smart Contract (GoPlus)**:\n"
    if not goplus_data:
        goplus_section += "   ⚠️ Không thể lấy dữ liệu bảo mật.\n"
        honeypot_risk = True # Assume risk if no data
    else:
        is_honeypot = goplus_data.get("is_honeypot")
        buy_tax = goplus_data.get("buy_tax", 0)
        sell_tax = goplus_data.get("sell_tax", 0)
        
        if is_honeypot:
            goplus_section += "   ❌ **CẢNH BÁO MÃ ĐỘC (HONEYPOT)**: Không thể bán!\n"
            honeypot_risk = True
        else:
            goplus_section += "   ✅ Không phát hiện Honeypot.\n"
            honeypot_risk = False
            
        tax_str = f"Thuế Mua: {buy_tax}% | Thuế Bán: {sell_tax}%"
        if buy_tax is not None and sell_tax is not None:
            if buy_tax > 10 or sell_tax > 10:
                goplus_section += f"   ⚠️ {tax_str} (Thuế cao!)\n"
            else:
                goplus_section += f"   ✅ {tax_str}\n"
        else:
            goplus_section += "   ⚠️ Không rõ thông tin Thuế giao dịch.\n"

    # 2. Format DexScreener Market Data
    market_section = "\n📈 **Chỉ số Market (DexScreener)**:\n"
    liquidity_risk = False
    wash_trading_risk = False
    
    if not dex_data:
        market_section += "   ⚠️ Không có dữ liệu thị trường trực tiếp.\n"
        liquidity_risk = True # Assume risk
    else:
        liquidity = dex_data.get("liquidity.usd", 0)
        volume_24h = dex_data.get("volume.h24", 0)
        market_cap = dex_data.get("marketCap", 0)
        
        market_section += f"   💧 Thanh khoản (Liquidity): ${liquidity:,.0f}\n"
        market_section += f"   📊 Khối lượng 24h (Volume): ${volume_24h:,.0f}\n"
        
        if market_cap:
            market_section += f"   🌐 Vốn hóa (Market Cap): ${market_cap:,.0f}\n"

        websites = dex_data.get("websites", [])
        socials = dex_data.get("socials", [])
        social_str = f"🌐 Website: {len(websites)} | 📱 MXH: {len(socials)}"
        if len(websites) == 0 and len(socials) == 0:
            market_section += f"   ❌ **BÁO ĐỘNG**: KHÔNG CÓ CỘNG ĐỒNG (0 Website, 0 Social). Khả năng cao là rác!\n"
        else:
            market_section += f"   ✅ {social_str}\n"
            
        # Liquidity Check
        if liquidity < 10000:
            market_section += "   ❌ **CẢNH BÁO RỦI RO BAY MÀU (RUG PULL)**: Thanh khoản quá thấp (< $10k).\n"
            liquidity_risk = True
        elif market_cap and market_cap > 0 and (liquidity / market_cap) < 0.05:
            market_section += "   ⚠️ **CẢNH BÁO**: Thanh khoản mỏng (< 5% Market Cap), dễ bị thao túng giá.\n"
            liquidity_risk = True
        else:
            market_section += "   ✅ Thanh khoản ở mức ổn định.\n"
            
        # Wash Trading Check
        if liquidity > 0 and (volume_24h / liquidity) > 5:
            market_section += "   ⚠️ **CẢNH BÁO WASH TRADING**: Volume cao gấp >5 lần thanh khoản, có dấu hiệu tạo volume giả!\n"
            wash_trading_risk = True

    # 3. Format Deployer Data
    deployer_section = "\n🕵‍♂️ **Phân tích Deployer (Creator)**:\n"
    deployer_risk = False
    if not deployer_data:
        deployer_section += "   ⚠️ Không thể phân tích lịch sử người tạo.\n"
    else:
        creator = deployer_data.get("creator_address")
        score = deployer_data.get("credibility_score", 100)
        funded_by_tornado = deployer_data.get("funded_by_tornado", False)
        spam_risk = deployer_data.get("spam_token_risk", False)
        abnormal_transfers = deployer_data.get("abnormal_transfers", False)
        
        if creator:
            deployer_section += f"   👤 Ví: `{creator}`\n"
        
        deployer_section += f"   🎯 Điểm Tín Nhiệm: {score}/100\n"
        
        if funded_by_tornado:
            deployer_section += "   ❌ **BÁO ĐỘNG ĐỎ**: Nguồn tiền deploy đến từ Mixer (Tornado Cash)!\n"
            deployer_risk = True
        if spam_risk:
            deployer_section += "   ⚠️ **CẢNH BÁO**: Ví này deploy hàng loạt token rác trong 30 ngày qua.\n"
            deployer_risk = True
        if abnormal_transfers:
            deployer_section += "   ⚠️ **CẢNH BÁO**: Dấu hiệu phân phát token ảo (Airdrop mờ ám / Gom ví cá mập).\n"
            deployer_risk = True
            
        if not (funded_by_tornado or spam_risk or abnormal_transfers):
            deployer_section += "   ✅ Lịch sử Deployer khá sạch, chưa thấy cờ đỏ.\n"

    # 4. Format Holders Data
    holders_section = "\n🐋 **Phân bổ Token (Top Holders)**:\n"
    holders_risk = False
    if not holders_data:
        holders_section += "   ⚠️ Không thể phân tích lượng phân bổ token.\n"
    else:
        top_10 = holders_data.get("top_10_percentage", 0)
        risk_level = holders_data.get("risk_level", "Medium")
        
        holders_section += f"   🍩 Mức độ tập trung Top 10 ví: {top_10:.2f}%\n"
        if risk_level == "Extreme":
            holders_section += "   ❌ **CẢNH BÁO RUG-PULL**: Top 10 ví nắm trên 80% cung lưu hành!\n"
            holders_risk = True
        elif risk_level == "High":
            holders_section += "   ⚠️ **RỦI RO CAO**: Top 10 ví nắm trên 50% cung. Cẩn thận cá mập xả hàng.\n"
            holders_risk = True
        elif risk_level == "Medium":
            holders_section += "   ⚠️ Mức độ phân bổ trung bình (>30%).\n"
        else:
            holders_section += "   ✅ Phân bổ token khá tốt (Top 10 < 30%).\n"

    # 5. Format AI Report
    ai_section = f"\n🤖 **Phân tích Mã nguồn (AI)**:\n"
    ai_risk = False
    if "❌ RISK ALERT" in ai_report or "failed" in ai_report.lower():
        ai_section += f"   ❌ Lỗi: {ai_report.strip()}\n"
        ai_risk = True
    else:
        # Assuming the AI report is already formatted, we just trim or extract key points
        # For a quick scan, we append a truncated version or highlight risks
        if "High" in ai_report or "Critical" in ai_report or "Scam" in ai_report:
            ai_section += "   ❌ AI phát hiện Lỗ hổng / Rủi ro nghiêm trọng trong Smart Contract!\n"
            ai_risk = True
        else:
            ai_section += "   ✅ AI không phát hiện điểm đáng ngờ nghiêm trọng trực tiếp.\n"

    # 6. Final Conclusion
    conclusion = "\n⚖️ **KẾT LUẬN CUỐI CÙNG**: "
    reason = ""
    
    if honeypot_risk:
        conclusion += "❌ **TRÁNH XA (SCAM LIKELY)**"
        reason = "Token là Honeypot (Chỉ được mua, không cho bán)."
    elif deployer_data and deployer_data.get("funded_by_tornado"):
        conclusion += "❌ **TRÁNH XA (SCAM DEPLOYER)**"
        reason = "Ví người tạo sử dụng tiền ẩn danh từ Tornado Cash (99% là Scammer)."
    elif liquidity_risk and wash_trading_risk:
        conclusion += "❌ **TRÁNH XA (HIGH RISK)**"
        reason = "Thanh khoản ảo (Wash Trading) kết hợp thanh khoản quá mỏng, nguy cơ sập giá bất cứ lúc nào."
    elif holders_risk:
        conclusion += "❌ **CẢNH BÁO XẢ HÀNG (DUMP RISK)**"
        reason = "Lượng token bị kiểm soát quá nhiều bởi một số ít cá mập (Top Holders)."
    elif liquidity_risk:
        conclusion += "⚠️ **RỦI RO CAO (HIGH RISK)**"
        reason = "Thanh khoản quá thấp, dễ bị Rug-pull hoặc trượt giá nặng."
    elif deployer_risk:
        conclusion += "⚠️ **RỦI RO CAO (SUSPICIOUS CREATOR)**"
        reason = "Lịch sử người tạo token rất đáng ngờ (Nhả token rác hoặc phân phát ảo)."
    elif ai_risk:
        conclusion += "⚠️ **CẨN THẬN (WARNING)**"
        reason = "Phát hiện mã nguồn ẩn chứa rủi ro hoặc không minh bạch (Unverified)."
    elif wash_trading_risk:
        conclusion += "⚠️ **CẨN THẬN (WARNING)**"
        reason = "Volume giao dịch chủ yếu là bot tự mua/bán nhằm thu hút Fomo."
    else:
        conclusion += "✅ **CÓ THỂ QUAN SÁT THÊM / NÊN ĐẦU TƯ (SAFE CƠ BẢN)**"
        reason = "Không phát hiện mã độc Honeypot, thanh khoản ổn định và chưa có dấu hiệu bất thường rõ ràng."

    final_report = (
        f"🔍 **AntiGravity Quick Scan**\n"
        f"🔗 Mạng: Ethereum | Token: `{token_address}`\n\n"
        f"{goplus_section}"
        f"{market_section}"
        f"{deployer_section}"
        f"{holders_section}"
        f"{ai_section}"
        f"{conclusion}\n"
        f"📝 **Lý do**: {reason}"
    )
    
    return final_report
