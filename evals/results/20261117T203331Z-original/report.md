# Eval report: `original`

- Generated: 2026-11-17 20:33 UTC
- Runs: 10 (10 cases x 1 repeats); deterministic checks only (no LLM judge in this report)

| Metric | Value |
|---|---|
| HTTP 200 | 100% |
| Routing (expected agents used) | 100% |
| Tools (expected tools called) | 100% |
| Content (must-include terms) | 100% |
| All checks passed | 100% |
| Latency p50 / p95 | 42.7s / 68.0s |
| LLM calls per chat (mean) | 5.7 |
| Cost per chat (mean / total) | US$ 0.1218 / US$ 1.2175 |

## Per case

| Case | Pass (runs) | Agents | Tools | Notes |
|---|---|---|---|---|
| O01 | 1/1 | supervisor, knowledge | ask_knowledge, search_kb |  |
| O02 | 1/1 | supervisor, knowledge | ask_knowledge, get_weather |  |
| O03 | 1/1 | supervisor, support | ask_support, get_receivables, get_sales_summary |  |
| O04 | 1/1 | supervisor, knowledge | ask_knowledge, search_kb |  |
| O05 | 1/1 | supervisor, knowledge, support | ask_knowledge, ask_support, get_terminal_status, get_tickets, search_kb |  |
| O06 | 1/1 | supervisor, knowledge | ask_knowledge, search_kb |  |
| O07 | 1/1 | supervisor, knowledge | ask_knowledge, get_exchange_rate |  |
| O08 | 1/1 | supervisor, support | ask_support, get_recent_transactions, get_terminal_status, lookup_decline_code |  |
| O09 | 1/1 | supervisor, knowledge | ask_knowledge, search_kb |  |
| O10 | 1/1 | supervisor, knowledge | ask_knowledge, search_kb |  |

## Answers (first repeat)

### O01: What's the difference between the Get Clássica and the Get Smart?

Both machines take the same payments. The main differences are connectivity, printing and the screen. The Get Smart is Getnet's most complete model, and the Get Clássica is the simpler one with a built-in printer.

| | **Get Clássica** | **Get Smart** |
|---|---|---|
| **Positioning** | Made with recycled material [S9] | "The most modern and complete" Getnet machine [S9] |
| **Payment methods** | Contactless (tap to pay), QR Code and Pix [S9] | Contactless, QR Code and Pix, plus chip and magnetic stripe readers [S9][S4] |
| **Connectivity** | 3G and Wi‑Fi. Comes with a 3G SIM chip that has a free data plan [S9][S5] | 4G, Wi‑Fi and Bluetooth. Comes with a 4G SIM chip that has a free data plan [S4] |
| **Printing** | Built-in printer, with 2 paper rolls in the box [S9][S5] | Sources don't say it has a printer. No paper roll is listed for it [S9] |
| **Screen and buttons** | Physical buttons [S5] | Touchscreen [S4] |
| **Extra features** | None listed | Issues invoices (nota fiscal), shows sales reports on the machine, runs apps such as digital order pads, and has a self-service (kiosk) mode [S9][S7][S6] |
| **Best for** | Not stated | Businesses on the move, like bars, restaurants and street vendors [S7][S8] |

**Price:** Both are advertised as free. To qualify, you have to open a Get Conta, meet a minimum sales volume and receive your payments in 2 days [S9]. Getnet's materials don't list the per-sale fees for either model. You can check your fees in the Getnet app or the Portal do Cliente under "Produtos contratados e taxas" [S10].

**Quick tip:** If you need printed receipts or printed installment simulations, the Clássica is the safer choice [S2]. If you want more features and 4G, go with the Smart.

Getnet's materials don't confirm whether the Smart can print, and they disagree on its mobile network (the rental page lists 3G, the manual mentions only 4G). It's worth checking both points and current pricing with Getnet before you sign up.

### O02: What's the weather forecast in Porto Alegre tomorrow?

Tomorrow (Wednesday, Nov 18) Porto Alegre is expected to have **thunderstorms with hail** [S1].

- **Temperature:** low of 21.7 °C, high of 30.5 °C
- **Chance of rain:** 82%, about 9.7 mm
- **Wind:** up to 12.5 km/h

Bring an umbrella, stay indoors during storms and park under cover if you can because of the hail.

This comes from the Open-Meteo forecast and could change, so check it again tomorrow morning.

### O03: When will the money from yesterday's sales be deposited?

Yesterday's sales (Mon 16/11) will be paid in three parts, totaling **R$ 2.934,66 net**:

| When | Method | Gross | Fees | Net | Status |
|---|---|---|---|---|---|
| 16/11 (same day) | Pix | R$ 327,18 | R$ 3,24 | R$ 323,94 | **Paid** |
| **17/11 (today)** | Debit (next business day) | R$ 2.084,12 | R$ 28,56 | R$ 2.055,56 | Scheduled |
| 16/12/2026 | Credit 1x (30 days) | R$ 573,23 | R$ 18,07 | R$ 555,16 | Scheduled |

All of this goes to your Conta Getnet •••• 1988.

**Two other things you should know:**
- **Today's debit payment hasn't arrived yet:** the R$ 2.055,56 still shows as scheduled for today and isn't marked as paid.
- **Possible double charge:** sales S-1988-01225 and S-1988-01226 were each R$ 239,90 on the same Mastercard ending in 8812, made 1 minute apart on terminal T-1988-02. Please check whether your customer really bought twice. If they didn't, I can pass this to a specialist.

One credit sale of R$ 158,90 at 17:40 was declined (code 51), so you won't be paid for that one.

### O04: Do I need a bank account to receive my sales via Pix?

**Yes, in practice you need an account.** To receive Pix sales with Getnet, you register a Pix key that's linked to the account where you want the money to go. A Pix key always points to an account, so you can't receive Pix sales without one [S2].

**Which accounts work:**
- **Get Conta (Getnet's own account):** you can register your key in the Getnet Brasil app under Conta > Pix > Minhas Chaves > Cadastrar chave [S2].
- **An account at another bank:** checking, savings or prepaid payment accounts can all work. That bank's Pix service must be integrated with Getnet, so check with Getnet's Central de Atendimento first [S2].

**How to start:**
1. Register a Pix key on your account. It can be your CPF/CNPJ, email, phone number or a random key. If you have several, give Getnet just one [S2].
2. Turn on Pix in the Getnet Brasil app or on the Portal Minha Conta, using that same key [S2][S3]. The app shows which account receives your Pix payments [S1].
3. On the card machine, go to Pagamento, enter the amount and choose Pix. Your customer scans the QR Code, and you wait for the success screen [S3].

Getnet's official content doesn't say how long Pix sales take to reach your account or what the fees are. Its list of supported banks also dates from 2020. Please confirm these points with Getnet support.

### O05: My card machine won't connect to the internet, what should I do?

The machine that isn't connecting is most likely your **Get Smart (T-1988-01)**. It uses Wi-Fi and has been offline since 12:00 today. Your **Get Clássica (T-1988-02)** shows as online, but it last connected at 15:00.

**Try these steps on the Get Smart:**
1. **Check the store's Wi-Fi.** Make sure the internet is working on another device and that the network name or password hasn't changed.
2. **Reconnect the machine.** Go to **Configurar → Conexões** (settings → connections) and choose your Wi-Fi network again. Type the password carefully [S1][S3].
3. **Run Teste de Conexão** (connection test) on that same screen [S3].
4. **Try the 4G chip.** If the Wi-Fi still doesn't work, check the chip on that same Conexões screen [S3].
5. **If an error code appears:**
   - **ADQ 4-30 or 4-27:** press Function → **38** → **Inicialização** (initialization), then do a test sale [S12][S16].
   - **ADQ 1-18:** press Function → **25** → enter the operator password → Function **46**, then do a test sale [S8].

   These codes are listed for Getnet machines in general, so the menu may be different on the Get Smart.

**If it still won't connect:**
- **Ask for maintenance:** go to **Minha Getnet** → select the machine model → **Solicitar manutenção** (request maintenance). You'll get a protocol number [S6].
- **Call support (6am–9pm):**
  - Capitals: 4002-4000 / 4003-4000
  - Other cities: 0800-648-8000
  - WhatsApp: 11 97694-6815 [S7]
- **Or ask me to open a support ticket** for you.

I can't see whether there's a network outage right now. Getnet's guides also don't explain how to restart the machine. Since the Get Clássica's status may be out of date, do a test sale on it as well.

### O06: How does receivables advance (antecipação) work with Getnet?

With antecipação, Getnet pays you money from your sales before their normal payout date. There are two types: **automatic**, where your sales are advanced on an ongoing basis, and **punctual (eventual)**, where you ask for an advance only when you want one.

**What can be advanced**
- Single-payment and installment credit sales [S2]. A newer Getnet page also lists debit and Pix sales, all requested in the app [S6].
- It's meant to help your cash flow by bringing in money you'd otherwise wait 30, 60, 90 days or more for. One example is after busy periods like Black Friday [S6].

**Automatic advance**
- It's a credit approval, so Getnet reviews each contract and can say no [S2].
- If you're on the "Receba Conforme suas Vendas" plan, you need automatic advance to get that plan's fee exemption [S2].
- How to turn it on (from Getnet help pages found on the web). You need an admin profile and your [segredo removido] **Getnet Brasil app:** Serviços → Antecipação Automática → Habilitar, then accept the terms and confirm.
  - **Portal (Minha Conta):** Produtos e Serviços → Antecipação Automática → Habilitar. You can track the request under Meus pedidos → Atendimentos.
- Turning it on is free. Approval can take up to 48 hours, and an advance only happens when your balance is at least R$ 50.

**Punctual advance**
- An older Getnet page says you can simulate and request an advance in the app or on the card machine. I didn't find current step-by-step instructions.

**Fees**
- Advanced sales are charged a separate advance fee [S7]. Getnet's official content doesn't give the current rate.
- Getnet's official content does mention 2.73% per month on the "2 dias úteis" plan, but that's an extra fee on installment sales and may not be the advance rate [S2].
- To see your actual rate, check the app or the Portal do Cliente under **"Produtos contratados e taxas"** [S2].

**When the money arrives**
- An older Getnet page (around 2021) says advanced money arrives in 1 business day. Getnet's official content doesn't confirm a current timeframe.

**Note:** if your receivables are pledged to a bank as loan collateral (a "gravame"), that changes where your payouts go [S2].

Getnet's official content only covers this topic in general terms. The how-to steps, the R$ 50 minimum and the timing come from Getnet pages on the web, some of them older, so please check them in your app or Portal. If you'd like, I can look up your upcoming receivables to see what's available to advance.

### O07: What's the euro exchange rate today?

Today (17/11/2026), the euro's official PTAX rate from Banco Central do Brasil is **R$ 6,3659 to sell and R$ 6,3647 to buy**, per €1 [S1].

- This is the closing rate, published at 13:07 [S1].
- PTAX is only a reference rate. Banks, exchange offices and card payments converted to another currency at the machine (DCC) use their own rates, which usually include an extra margin (spread) [S1].

### O08: My card machine is showing a transaction decline error.

I can't see a decline from the last few minutes in your account, so I can't yet tell which error your machine is showing. Here's what I found:

**Your machines (checked at 17:32)**
- **T-1988-01 (Get Smart, Wi‑Fi): offline since 12:00.** It can't process payments right now. Check the Wi‑Fi connection and restart it.
- **T-1988-02 (Get Clássica, 4G):** shows as online, but it hasn't contacted Getnet since 15:00. Restart it and check the 4G signal.

**Declines recorded today**
- **09:12, T-1988-02:** R$ 42,50, Elo debit card ending 7310, **code 57**. This card doesn't allow this type of transaction. Ask for another payment method and don't try the same card again.
- **R$ 416,25, T-1988-01:** Elo debit card ending 9533, **code 51**. The customer didn't have enough balance or limit. Offer another card or Pix. The customer can try again.
  - This record's time is 19:04, which hasn't happened yet, and the machine has been offline since 12:00. It's probably a sync error, so it may not be the decline you're seeing now.

Since neither machine has contacted Getnet recently, the error on your screen probably hasn't reached our systems yet.

**Which machine is showing the error, and what's the exact message or code on the screen?** With that, I can tell you what it means and what to do. If it still fails after a restart, I can pass the offline machine and the wrong timestamp to a support specialist.

### O09: How many installments can I split a sale into with the crediário?

With Getnet's Crediário you can split a sale into **up to 48 installments** [S1][S3]. That's the maximum. The customer's card issuer sets its own installment limit and interest rate for each card, so some customers may get fewer [S1][S3].

**How it works:**
- **Your customer** pays the interest, at a rate set by their card issuer [S1][S3].
- **You** get the full sale amount in one payment within 2 business days, however many installments the customer chooses. Only your discount fee (MDR) is taken out, and you can see that fee in the Getnet Brasil app or the Customer Portal [S1][S3].
- **Approvals:** Getnet has to review and turn on Crediário for your business, and the issuer has to approve each sale [S3].
- **Simulation:** Before the sale, you can show the customer every installment and the total cost. Insert the card, enter the amount, then choose **Crédito > Crediário**. The simulation is only a quote until the issuer approves the sale [S1][S3].
- **Machine rental:** Crediário sales don't count toward the monthly sales needed to skip the machine rental fee [S7].

**Other installment options:**
- **Parcelado Emissor:** up to 24x, and the customer pays the interest [S3].
- **Parcelado Lojista:** up to 12x with no interest for the customer. You're paid each installment monthly, starting 31 days after the sale [S3].

Getnet's content doesn't say what the minimum number of installments is.

### O10: Can I sell through WhatsApp using the Payment Link?

**Yes. You can sell on WhatsApp by sending your customer a Getnet Payment Link** [S2][S6].

**How it works**
1. Create the link in the **Getnet Brasil app** or the **Customer Portal** [S6].
2. Pick the payment methods: debit, credit (one payment or installments), Pix or digital wallets [S6].
3. Send the link in a WhatsApp chat. You can also share it by SMS, email or social media [S6][S9].
4. Your customer opens a secure page and pays there. They don't need an app or an account [S2][S7].
5. Track your sales in the app under "Vendas do dia" (today's sales) or in the Portal [S9][S11].

You don't need a website or a card machine, and the payment page has anti-fraud protection [S6][S7]. Payments inside WhatsApp Business itself have ended, so customers now pay through the link instead [S6].

**Good to know**
- **Payout timing:**
  - Link sales can't be paid out the same day. Same-day payout only applies to in-person sales [S4].
  - After 6 months of using links, you can ask to be paid in 2 days, and Getnet will review your request [S1].
- **Inactivity:** if you go 4 months without a sale, your link access is turned off and you'd have to go through approval again [S1].
- **Fees:** Getnet's website mentions R$ 1,00 per paid link or R$ 28/month, but it doesn't explain these options fully. They also depend on your contract.

My sources don't list your exact fees, payout times for each payment method, or the maximum number of installments. You can check these in your contract in the Getnet Brasil app or Customer Portal.

