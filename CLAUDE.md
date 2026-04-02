# RepairXpertIndAutomation — Industrial Fault Diagnosis

## Status: MVP BUILT — $0 revenue — CUSTOMERS WAITING (highest ROI)

## Stack
- Backend: FastAPI + Jinja2 (port 8300)
- Database: SQLite (diagnosis_log.db)
- AI: LM Studio — GLM-4v-flash (vision, port 8766) + Qwen 3.5 9B (text, port 1234)
- UI: Mobile-first dark theme for field technicians
- Launch: `run.bat` or `uvicorn indauto.app:app --port 8300`

## Assets
- 71 fault codes (27 Allen-Bradley), 6 equipment profiles
- 500+ industrial parts catalog (Allen-Bradley, IFM, Banner, ABB, Siemens, Omron, SMC, Pilz)
- Amazon Affiliate tag: "repairxpert-20" (2-8% commission on all parts links)
- Suppliers: **AutomationDirect (PRIMARY — goto supplier)**, Amazon (affiliate repairxpert-20), Grainger, Digikey, McMaster-Carr
- 50+ past diagnoses in history

## Revenue Actions (priority order)
1. ~~Add pricing page (Basic free, Pro $19.99/mo, Enterprise $49.99/mo)~~ DONE
2. ~~Integrate Stripe for payment~~ DONE — set env vars to activate
3. Onboard waiting customers
4. Track Amazon affiliate click-through
5. Add more equipment profiles (pilers, conveyors, AS/RS, packaging)

## Stripe Setup (required env vars)
- `STRIPE_SECRET_KEY` — from Stripe Dashboard > Developers > API keys
- `STRIPE_PUBLISHABLE_KEY` — same location (starts with pk_)
- `STRIPE_PRICE_ID_PRO` — create a $19.99/mo recurring product in Stripe, copy the price ID
- `STRIPE_PRICE_ID_ENTERPRISE` — create a $49.99/mo recurring product in Stripe, copy the price ID

## Key Patterns
- Photo upload → AI vision analysis → fault code match → parts recommendation
- LM Studio must be running for AI features (port 1234 for text, 8766 for vision)
- Confidence threshold: 0.6, max 5 causes per request, 60s timeout

## Future Features (deferred)
- Auto fault assistant from photo + code
- PLC logic interpreter
- Visual sensor diagnostics
- Multi-equipment worker nodes
