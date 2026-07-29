"""
Append Update Log entries to existing reports and rename to 2026-07-29.
Market context: July 28, 2026 — massive rotation out of chips/AI into value/defensive.
Memory stocks crashed (SK Hynix earnings miss), DELL -15% (customer concentration risk),
but Dow hit ATH, KO +5% on earnings beat.
"""
import os, re
from pathlib import Path
from datetime import date

REPORTS_DIR = Path(__file__).parent.parent / "reports"
TODAY = "2026-07-29"

# Update log content for each ticker (based on 7/28 close data + market context)
UPDATES = {
    "ALGM": """### 2026-07-29

| Metric | Value |
|---|---|
| **Price** | $44.13 |
| **1-Week** | -9.8% |
| **1-Month** | -32.9% |

> [!tip] Recent Developments
> - **Price Action:** ALGM continues its steady decline, down 9.8% this week and 32.9% over the past month, approaching its 52-week low of $42.01. The stock is deeply out of favor amid the broader semiconductor rotation.
> - **Key News:** No company-specific catalysts. The weakness reflects sector-wide pressure on auto/industrial semis as macro concerns mount.
> - **Peer/Sector Context:** The Philly Semi Index (SOX) fell 4.49% on July 28 alone. Auto chip peers are similarly under pressure, with the market rotating away from cyclicals into defensive names.
> - **Short-Term Outlook:** ALGM is in a technical breakdown; watch for support at the $42 level (52-week low). A break below could accelerate selling.

> [!quote] Rating Status
> **Maintain Caution** — No fundamental thesis change, but price action is deteriorating. The 33% monthly decline suggests structural selling pressure beyond normal sector rotation.
> Next catalyst: Monitor auto/industrial demand signals and any company guidance updates.""",

    "AMZN": """### 2026-07-29

| Metric | Value |
|---|---|
| **Price** | $230.86 |
| **1-Week** | -6.7% |
| **1-Month** | -3.9% |

> [!tip] Recent Developments
> - **Price Action:** AMZN fell 6.7% this week, underperforming the Dow but faring better than most tech peers. The stock is down only 3.9% monthly, showing relative resilience.
> - **Key News:** No major AMZN-specific news. Cloud competition and AI CapEx concerns persist as a sector-wide overhang, with MSFT earnings (July 29) serving as a bellwether for cloud demand.
> - **Peer/Sector Context:** The "Magnificent Seven" were mixed — GOOGL +2.2%, MSFT +1.1%, while chip-exposed names led the selloff. AMZN's diversified model (e-commerce + AWS + advertising) provides some insulation from pure AI sentiment swings.
> - **Short-Term Outlook:** AWS growth trajectory and AI monetization progress are the key narratives. MSFT's cloud numbers will set the tone.

> [!quote] Rating Status
> **Maintain Constructive** — Relatively defensive within big tech. AWS remains the crown jewel; watch for Q2 earnings to validate the AI investment thesis.
> Next catalyst: Q2 2026 earnings; MSFT cloud results as read-through.""",

    "AVGO": """### 2026-07-29

| Metric | Value |
|---|---|
| **Price** | $380.91 |
| **1-Week** | -1.4% |
| **1-Month** | +2.3% |

> [!tip] Recent Developments
> - **Price Action:** AVGO is a standout — only down 1.4% on the week and up 2.3% over the month, dramatically outperforming the SOX index (-4.49% on July 28 alone). The stock is consolidating near its 52-week highs.
> - **Key News:** Broadcom's diversified model (networking, software, storage) and strong VMware integration continue to differentiate it from pure-play memory/AI server names that got crushed.
> - **Peer/Sector Context:** While MRVL (-16.1% weekly), DELL (-15% single day), and memory stocks crashed, AVGO's relative strength highlights the market's preference for profitable, cash-flow-rich compounders over high-beta AI plays.
> - **Short-Term Outlook:** The stock is in a comfortable consolidation range ($372-$407). A breakout above $407 would be technically bullish; support at $372.

> [!quote] Rating Status
> **Maintain Constructive** — AVGO remains one of the highest-quality names in semis. The VMware accretion story and AI networking demand provide strong fundamental support.
> Next catalyst: Q3 FY2026 earnings; AI ASIC customer ramp updates.""",

    "CGNX": """### 2026-07-29

| Metric | Value |
|---|---|
| **Price** | $60.36 |
| **1-Week** | -4.1% |
| **1-Month** | -11.7% |

> [!tip] Recent Developments
> - **Price Action:** CGNX fell 4.1% this week to $60.36, approaching the 52-week low of $57.70. The stock has been grinding lower with no meaningful bounce, reflecting the market's negative view on industrial automation exposure.
> - **Key News:** No company-specific news. The macro backdrop continues to weigh on factory automation and capital equipment names.
> - **Peer/Sector Context:** Industrial/automation names are broadly out of favor as PMI data remains soft and tariff uncertainty weighs on CapEx decisions. CGNX's machine vision products are highly cyclical.
> - **Short-Term Outlook:** Watch for a test of the $57.70 support level. Any positive manufacturing data or trade policy clarity could trigger a sharp relief rally given oversold conditions.

> [!quote] Rating Status
> **Maintain Wait-and-See** — Valuation is compressing but the macro headwinds are real. A bottom will likely require improved industrial data.
> Next catalyst: Monthly manufacturing PMI; trade policy developments.""",

    "CRCL": """### 2026-07-29

| Metric | Value |
|---|---|
| **Price** | ~$61.50 |
| **1-Week** | -9.5% |
| **1-Month** | -15.3% |

> [!tip] Recent Developments
> - **Price Action:** CRCL dropped 9.5% on the week, accelerating its month-long decline to 15.3%. The stock is trading near the bottom of its recent range.
> - **Key News:** No company-specific catalysts identified. The decline appears driven by broader small/mid-cap growth de-rating in the current risk-off environment.
> - **Peer/Sector Context:** Small-cap and speculative growth names are bearing the brunt of the rotation out of risk assets. The SOX selloff has spilled over into adjacent tech.
> - **Short-Term Outlook:** Low-volume selloffs in small caps can reverse quickly if sentiment shifts, but without a catalyst, the path of least resistance remains lower.

> [!quote] Rating Status
> **Monitor** — Low liquidity and high beta make this a risk-on/risk-off trade. Position sizing discipline is critical.
> Next catalyst: Company-specific news flow; macro sentiment shift.""",

    "DELL": """### 2026-07-29

| Metric | Value |
|---|---|
| **Price** | ~$380 (est.) |
| **1-Week** | ~-18% |
| **1-Month** | ~-20% |

> [!tip] Recent Developments
> - **Price Action:** DELL suffered a catastrophic ~15% single-day plunge on July 28, one of the worst performers in the entire market. The stock has now lost roughly 20% in a month.
> - **Key News:** **Evercore analyst flagged critical customer concentration risk** — an estimated ~70% of Dell's projected $60B in AI server revenue may come from just three customers: CoreWeave, SpaceXAI, and IREN. This revelation, combined with China AI competition fears, triggered a massive deleveraging.
> - **Peer/Sector Context:** The AI server thesis is under intense scrutiny. SMCI also fell 4.6%, and the broader AI infrastructure buildout narrative is being questioned as CapEx ROI concerns mount.
> - **Short-Term Outlook:** The concentration risk revelation is a significant overhang. Even if Dell wins more customers, the market will now discount the AI server revenue stream more heavily until diversification is proven.

> [!quote] Rating Status
> **Downgrade to CAUTIOUS** — The customer concentration risk fundamentally alters the risk/reward. A single customer pullback could devastate the AI server revenue stream.
> Next catalyst: Diversification of AI server customer base; Q2 FY2027 earnings.""",

    "GOOGL": """### 2026-07-29

| Metric | Value |
|---|---|
| **Price** | $333.71 |
| **1-Day** | +2.19% |
| **Notes** | Bucked the tech selloff |

> [!tip] Recent Developments
> - **Price Action:** GOOGL was one of the few tech winners on July 28, rising 2.19% to $333.71, significantly outperforming the Nasdaq (-0.22%). The stock is showing relative strength in a risk-off tape.
> - **Key News:** No company-specific news. The move appears to be a rotation within mega-cap tech — money flowing from AI hardware/chip names into software/platform companies with more visible earnings streams.
> - **Peer/Sector Context:** The "AI exhaustion" trade is benefiting Google given its dominant search/ad position, cloud growth, and less direct exposure to the AI CapEx bubble that is punishing DELL, SMCI, and memory names.
> - **Short-Term Outlook:** Google is increasingly seen as a relative safe haven within big tech. The strong ad business and improving cloud margins provide a buffer against AI spending concerns.

> [!quote] Rating Status
> **Maintain Constructive** — Google's diversified revenue and improving profitability make it a relative outperformer in the current rotation. Cloud and AI integration remain key growth drivers.
> Next catalyst: Q2 2026 earnings; Google Cloud growth trajectory.""",

    "KO": """### 2026-07-29

| Metric | Value |
|---|---|
| **Price** | $88.27 |
| **1-Day** | +5.00% |
| **Notes** | All-time high on earnings beat |

> [!tip] Recent Developments
> - **Price Action:** KO surged 5.00% on July 28 to close at $88.27, hitting an intraday all-time high of $90.22. The stock was one of the Dow's top performers, driving the index to a 500+ point gain.
> - **Key News:** **Q2 2026 earnings beat** — adjusted EPS of $0.97 (+11% YoY), beating consensus. Management raised full-year profit guidance, citing strong global demand, effective pricing power, and improving margins.
> - **Peer/Sector Context:** Consumer staples are back in favor as the market rotates out of risk assets. KO's earnings-driven breakout validates the defensive rotation thesis — quality compounders with pricing power are being rewarded.
> - **Short-Term Outlook:** The breakout to ATHs on strong earnings is technically bullish. KO's global brand, pricing power, and dividend yield make it an attractive destination for capital fleeing volatile tech names.

> [!quote] Rating Status
> **Upgrade to POSITIVE** — Earnings beat + guidance raise + ATH breakout is a powerful combination. KO is executing well and benefiting from the rotation into defensives.
> Next catalyst: Sustained volume growth; EM demand recovery.""",

    "MRVL": """### 2026-07-29

| Metric | Value |
|---|---|
| **Price** | $174.47 |
| **1-Week** | -16.1% |
| **1-Month** | -37.2% |

> [!tip] Recent Developments
> - **Price Action:** MRVL suffered one of the worst weekly drawdowns in the semiconductor space, plunging 16.1% to $174.47. The monthly loss now stands at a staggering 37.2%, placing the stock firmly in bear market territory.
> - **Key News:** The selloff is driven by the broader AI chip rotation, exacerbated by China AI competition fears. As a key AI ASIC and data infrastructure play, MRVL is getting hit by the same "peak AI CapEx" narrative that crushed DELL and memory stocks.
> - **Peer/Sector Context:** The SOX fell 4.49% on 7/28, and MRVL underperformed even that. The stock's high beta and heavy AI exposure make it a prime target for de-risking. AVGO's relative resilience (-1.4%) highlights the divergence between diversified and pure-play AI semis.
> - **Short-Term Outlook:** A 37% monthly decline in a large-cap semi is extreme and historically suggests capitulation. A technical bounce is likely, but sustained recovery requires the AI CapEx narrative to stabilize.

> [!quote] Rating Status
> **Downgrade to CAUTIOUS** — While the long-term AI ASIC thesis remains intact, the magnitude of the drawdown and sector-wide sentiment shift demand respect. Wait for stabilization before adding.
> Next catalyst: Q2 FY2027 earnings; AI ASIC order pipeline updates.""",

    "MSFT": """### 2026-07-29

| Metric | Value |
|---|---|
| **Price** | $393.35 |
| **1-Week** | -1.1% |
| **1-Month** | +6.7% |

> [!tip] Recent Developments
> - **Price Action:** MSFT closed at $393.35, down just 1.1% on the week and still up 6.7% over the past month. The stock is showing strong relative strength as AI hardware names get crushed.
> - **Key News:** **MSFT reports Q4 FY2026 earnings on July 29 (today).** Consensus expects EPS of $4.24 on revenue of $87.62B. Azure growth, AI Copilot monetization, and CapEx trajectory are the key focus areas.
> - **Peer/Sector Context:** MSFT is positioned as a "show-me" story — the market wants to see AI investment translate into revenue growth. Unlike pure AI hardware plays, MSFT's diversified model (Office, Azure, LinkedIn, Gaming) provides earnings stability.
> - **Short-Term Outlook:** The earnings report tonight is a critical catalyst not just for MSFT but for the entire AI software/platform thesis. Strong Azure numbers could shift sentiment back toward AI beneficiaries. Weakness could accelerate the rotation out of tech.

> [!quote] Rating Status
> **HOLD into Earnings** — The stock is well-positioned fundamentally, but earnings tonight represent binary risk. We maintain our constructive view but recommend awaiting the print before adjusting.
> Next catalyst: Q4 FY2026 earnings (July 29 after close).""",

    "NVDA": """### 2026-07-29

| Metric | Value |
|---|---|
| **Price** | $197.01 |
| **1-Week** | -5.0% |
| **1-Month** | +1.0% |

> [!tip] Recent Developments
> - **Price Action:** NVDA closed at $197.01, down 5.0% on the week but essentially flat over the past month (+1.0%). The stock has been range-bound between $190-$214 as the market digests peak-AI-era valuation.
> - **Key News:** No NVDA-specific catalysts. The stock was caught in the broader semiconductor selloff (SOX -4.49% on July 28) but held up better than memory and AI server names. Apple briefly reclaimed the world's most valuable company title from NVDA.
> - **Peer/Sector Context:** The $1.6T wipeout in US tech stocks this week has NVDA at the epicenter. The market is increasingly asking: is the AI infrastructure buildout sustainable, or are we overbuilding? NVDA's answer will come with its next earnings.
> - **Short-Term Outlook:** NVDA is consolidating in a $190-$214 range. A break below $190 would be technically bearish; above $214 would signal renewed momentum. The range is likely to hold into earnings.

> [!quote] Rating Status
> **Maintain HOLD** — NVDA remains the undisputed AI king, but the stock is in a "prove it" phase. The next earnings cycle is critical to validate that demand is sustainable, not pulled forward.
> Next catalyst: Q2 FY2027 earnings (late August); Blackwell/Blackwell Ultra ramp updates.""",

    "ONDS": """### 2026-07-29

| Metric | Value |
|---|---|
| **Price** | ~$7.40 |
| **1-Week** | +2.6% |
| **1-Month** | -2.0% |

> [!tip] Recent Developments
> - **Price Action:** ONDS is a rare bright spot in small-cap tech, gaining 2.6% on the week while most peers sold off. The stock is roughly flat over the past month, showing surprising resilience.
> - **Key News:** No company-specific news. The relative strength suggests some underlying support, possibly from insider buying or niche catalysts in the drone/autonomous space.
> - **Peer/Sector Context:** Small-cap tech is under broad pressure, making ONDS's positive weekly performance noteworthy. However, low liquidity means price moves can be idiosyncratic and not necessarily signal-driven.
> - **Short-Term Outlook:** The relative strength is encouraging but needs confirmation with volume. A sustained move above $8.58 (week high) would be technically bullish.

> [!quote] Rating Status
> **Monitor** — Small-cap speculative name with limited visibility. The recent resilience is a positive sign but not yet a thesis-changer.
> Next catalyst: Company announcements; drone/autonomous sector catalysts.""",

    "ORCL": """### 2026-07-29

| Metric | Value |
|---|---|
| **Price** | ~$117 |
| **1-Week** | -5.6% |
| **1-Month** | -18.8% |

> [!tip] Recent Developments
> - **Price Action:** ORCL fell 5.6% on the week, extending its monthly decline to 18.8%. The stock is approaching its 52-week low of $114.50 after being one of the early AI cloud winners.
> - **Key News:** No company-specific news. The decline reflects the broader rotation out of enterprise tech and AI cloud names as CapEx ROI concerns mount.
> - **Peer/Sector Context:** Oracle's AI cloud narrative (OCI) is facing the same scrutiny as other AI infrastructure plays. The market is differentiating less between winners and losers in the current sell-first-ask-questions-later environment.
> - **Short-Term Outlook:** The 52-week low at $114.50 is critical support. A break below would signal a major technical breakdown. Oracle's sticky enterprise base and growing OCI backlog provide fundamental support.

> [!quote] Rating Status
> **Maintain HOLD** — Oracle's cloud transformation is real but the stock is caught in the AI sentiment downdraft. Valuation is becoming more attractive as the selloff deepens.
> Next catalyst: Q1 FY2027 earnings; OCI revenue growth and backlog updates.""",

    "PLTR": """### 2026-07-29

| Metric | Value |
|---|---|
| **Price** | $123.53 |
| **1-Week** | -6.9% |
| **1-Month** | +6.8% |

> [!tip] Recent Developments
> - **Price Action:** PLTR fell 6.9% on the week to $123.53, giving back some of its recent gains but still up 6.8% over the past month. The stock is consolidating in the mid-$120s after a strong run.
> - **Key News:** No company-specific news. PLTR continues to benefit from AI software adoption tailwinds, particularly in government and defense verticals where its AIP platform has strong traction.
> - **Peer/Sector Context:** PLTR is holding up better than most high-growth tech names, reflecting investor confidence in its government revenue visibility and expanding commercial AI use cases.
> - **Short-Term Outlook:** The $118-$135 range defines the near-term technical picture. A hold above $118 keeps the uptrend intact.

> [!quote] Rating Status
> **Maintain Constructive** — PLTR remains a differentiated AI play with sticky government contracts and accelerating commercial adoption. The relative strength vs. peers is a positive signal.
> Next catalyst: Q2 2026 earnings; AIP commercial customer growth metrics.""",

    "RKLB": """### 2026-07-29

| Metric | Value |
|---|---|
| **Price** | ~$64 |
| **1-Week** | -7.6% |
| **1-Month** | -34.8% |

> [!tip] Recent Developments
> - **Price Action:** RKLB fell 7.6% this week, bringing its monthly decline to a punishing 34.8%. The stock is now down ~58% from its May 2026 peak of ~$151, firmly in deep bear market territory.
> - **Key News:** No company-specific catalyst for the decline. The selloff reflects the broader rotation out of high-beta, capital-intensive growth names as interest rate expectations shift and risk appetite plummets.
> - **Peer/Sector Context:** Space stocks are deeply out of favor — a recent article noted three space stocks down more than 50% from highs. The sector's capital intensity and long-duration cash flows make it especially vulnerable to rising rate sensitivity.
> - **Short-Term Outlook:** A 58% drawdown from peak in a high-quality space name is extreme. Technical capitulation may be near, but catching a falling knife requires a catalyst — likely a successful launch or new contract win.

> [!quote] Rating Status
> **Maintain HOLD** — The long-term space economy thesis is intact, but the near-term price action is brutal. The stock is in the "despair" phase where fundamentals matter less than sentiment.
> Next catalyst: Successful Neutron rocket launch; major government/commercial contract wins.""",

    "SKHYV": """### 2026-07-29

| Metric | Value |
|---|---|
| **Price** | ~$130 |
| **1-Day** | -8.98% |
| **Notes** | Q2 earnings miss triggered memory selloff |

> [!tip] Recent Developments
> - **Price Action:** SK Hynix plunged 8.98% on July 28 after reporting Q2 results that missed analyst estimates. The ADR (SKHYV) was swept up in the broad memory-stock rout.
> - **Key News:** **Q2 2026 earnings miss** — Operating profit of ~60.5T KRW missed consensus of 64.2T KRW. Despite profit growing over 6x YoY, the market had priced in perfection. The miss triggered a cascading selloff across the entire memory sector, with WDC -14%, MU -8.9%.
> - **Peer/Sector Context:** The HBM cycle is being questioned — is the AI-driven demand sustainable, or are we at peak HBM pricing? SK Hynix's miss, however marginal, gives ammunition to the bears.
> - **Short-Term Outlook:** The earnings-driven selloff has technical significance. A quick recovery above $140 would be bullish; continued weakness below $125 signals deeper malaise.

> [!quote] Rating Status
> **Maintain CAUTIOUS** — The earnings miss is a warning sign for the entire HBM/memory complex. MU earnings will be the next critical read.
> Next catalyst: HBM4 qualification progress; MU earnings as sector read-through.""",

    "SMCI": """### 2026-07-29

| Metric | Value |
|---|---|
| **Price** | $28.45 |
| **1-Day** | -4.56% |
| **Notes** | China AI competition fears hit AI server names |

> [!tip] Recent Developments
> - **Price Action:** SMCI fell 4.56% on July 28 to $28.45, hitting an intraday low of $27.13. The stock continues to grind lower as the AI server thesis unravels in real time.
> - **Key News:** The selloff was triggered by China AI competition fears spreading from Asian chip stocks to US names, plus DELL's customer concentration revelation casting a shadow over the entire AI server industry. SMCI trades at a fraction of its former highs.
> - **Peer/Sector Context:** AI server stocks are in freefall — DELL -15%, SMCI -4.6% in a single day. The market is repricing the entire AI infrastructure supply chain as CapEx ROI concerns reach a fever pitch.
> - **Short-Term Outlook:** SMCI is a battleground stock. The fundamental AI demand story hasn't changed, but sentiment has completely soured. At $28, the market is pricing in significant downside to AI server forecasts.

> [!quote] Rating Status
> **Maintain CAUTIOUS** — The AI server thesis is under full-scale assault. SMCI's accounting history adds an extra layer of risk premium that the market is now pricing aggressively.
> Next catalyst: FY2026 Q4 earnings; AI server order book clarity.""",

    "SPCX": """### 2026-07-29

| Metric | Value |
|---|---|
| **Price** | $116.41 |
| **1-Week** | -5.8% |
| **1-Month** | -29.1% |

> [!tip] Recent Developments
> - **Price Action:** SPCX closed at $116.41, down 5.8% on the week and 29.1% over the past month. Despite the decline, the stock actually gained 2.56% on July 28, showing some stabilization.
> - **Key News:** No SpaceX-specific negative news. The monthly decline reflects the broader rotation out of high-growth, high-valuation private-tech-adjacent names. SpaceX's fundamental business (Starlink, launch) continues to execute well.
> - **Peer/Sector Context:** Space and private-tech proxies are deeply oversold. SPCX's 29% monthly decline is in line with RKLB (-34.8%), suggesting sector-wide de-rating rather than company-specific issues.
> - **Short-Term Outlook:** The +2.56% bounce on July 28 may signal near-term capitulation. SPCX remains one of the few ways to access SpaceX's growth, which provides a structural bid over time.

> [!quote] Rating Status
> **Maintain HOLD** — The SpaceX thesis is long-duration and largely uncorrelated with short-term market rotations. The 29% pullback improves the risk/reward for patient investors.
> Next catalyst: SpaceX funding rounds / valuation updates; Starlink subscriber growth.""",
}

def append_update_log(report_path: Path, ticker: str):
    """Append Update Log entry to an existing report."""
    content = report_path.read_text(encoding="utf-8")

    update_text = UPDATES.get(ticker)
    if not update_text:
        print(f"  SKIP {ticker}: no update data")
        return False

    # Check if this date already exists
    if f"### {TODAY}" in content:
        print(f"  SKIP {ticker}: already has {TODAY} entry")
        return False

    # Find the Update Log section or create it
    if "## 📝 Update Log" in content:
        # Insert before the last "---" before "Report generated"
        # Find insertion point: right after the last update log entry
        last_log_end = content.rfind("Next catalyst:")
        if last_log_end == -1:
            last_log_end = content.rfind("## 📝 Update Log")
            if last_log_end == -1:
                last_log_end = content.rfind("---\n\n*Report generated")
                if last_log_end == -1:
                    last_log_end = len(content)
                else:
                    # Insert before the final ---
                    pass
            else:
                # Find end of last entry
                pass
        else:
            # Find end of the last entry's paragraph
            end_of_entry = content.find("\n\n", last_log_end)
            if end_of_entry == -1:
                end_of_entry = last_log_end + 50

        # Actually, let's just insert right before the closing "---"
        closing = "\n---\n\n*Report generated"
        idx = content.rfind(closing)
        if idx == -1:
            # Try alternative footer
            closing = "\n---\n*Report generated"
            idx = content.rfind(closing)
        if idx == -1:
            # Just append at end
            new_content = content.rstrip() + "\n\n" + update_text + "\n"
        else:
            new_content = content[:idx] + "\n\n" + update_text + "\n" + content[idx:]
    else:
        # No update log section yet, insert before closing
        closing = "\n---\n\n*Report generated"
        idx = content.rfind(closing)
        if idx == -1:
            closing = "\n---\n*Report generated"
            idx = content.rfind(closing)
        if idx == -1:
            new_content = content.rstrip() + "\n\n---\n\n## 📝 Update Log\n\n" + update_text + "\n"
        else:
            new_content = content[:idx] + "\n\n---\n\n## 📝 Update Log\n\n" + update_text + "\n" + content[idx:]

    report_path.write_text(new_content, encoding="utf-8")
    return True

def main():
    updated = []
    for f in sorted(REPORTS_DIR.glob("*_report_*.md")):
        name = f.stem
        # Parse ticker
        ticker = name.split("_report_")[0]
        if ticker not in UPDATES:
            print(f"SKIP {f.name}: not in update list")
            continue

        print(f"Processing {ticker}...")
        if append_update_log(f, ticker):
            # Rename to today's date
            new_name = f"{ticker}_report_{TODAY}.md"
            new_path = f.parent / new_name
            if new_path != f:
                # Delete old file if renaming to new name
                f.rename(new_path)
                print(f"  Updated + renamed: {f.name} → {new_name}")
                updated.append(new_path)
            else:
                print(f"  Updated: {new_name}")
                updated.append(f)
        else:
            print(f"  No changes")

    print(f"\n{'='*50}")
    print(f"Updated {len(updated)} reports")
    for p in updated:
        print(f"  {p.name}")

if __name__ == "__main__":
    main()
