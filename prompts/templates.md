# LLM Prompt Templates

## Company Analysis Prompt

```
You are an equity research analyst. Analyze the following company data and produce:

1. **Executive Summary** (3-5 bullet points)
2. **Moat Assessment** — durable competitive advantages? (score 1-10)
3. **Key Risks** — what could break the thesis?
4. **Catalysts** — what could drive outperformance?
5. **Valuation Opinion** — over/under/fair valued vs peers & history

Company: {ticker}
Data: {company_data}
News: {recent_news}
Financials: {financials}
```

## News Sentiment Prompt

```
Classify each news headline for {ticker} with:
- Sentiment: bullish / bearish / neutral
- Impact: high / medium / low
- Relevance: direct / tangential

Headlines:
{headlines}
```

## Valuation Prompt

```
Given the following financial data for {ticker}, estimate intrinsic value
using DCF methodology. Explain key assumptions and sensitivity.

Data:
{financials}

Peers: {peers}
```
