# Eval report: `original`

- Generated: 2026-11-17 18:01 UTC
- Runs: 10 (10 cases x 1 repeats); deterministic checks only (no LLM judge in this report)

| Metric | Value |
|---|---|
| HTTP 200 | 100% |
| Routing (expected agents used) | 100% |
| Tools (expected tools called) | 100% |
| Content (must-include terms) | 100% |
| All checks passed | 100% |
| Latency p50 / p95 | 29.9s / 42.7s |
| LLM calls per chat (mean) | 5.0 |
| Cost per chat (mean / total) | US$ 0.1055 / US$ 1.0553 |

## Per case

| Case | Pass (runs) | Agents | Tools | Notes |
|---|---|---|---|---|
| O01 | 1/1 | supervisor, knowledge | ask_knowledge, search_kb |  |
| O02 | 1/1 | supervisor, knowledge | ask_knowledge, get_weather |  |
| O03 | 1/1 | supervisor, support | ask_support, get_receivables, get_sales_summary |  |
| O04 | 1/1 | supervisor, knowledge | ask_knowledge, search_kb |  |
| O05 | 1/1 | supervisor, knowledge, support | ask_knowledge, ask_support, get_terminal_status, search_kb |  |
| O06 | 1/1 | supervisor, knowledge | ask_knowledge, search_kb |  |
| O07 | 1/1 | supervisor, knowledge | ask_knowledge, get_exchange_rate |  |
| O08 | 1/1 | supervisor, support | ask_support, get_recent_transactions, get_terminal_status, lookup_decline_code |  |
| O09 | 1/1 | supervisor, knowledge | ask_knowledge, search_kb |  |
| O10 | 1/1 | supervisor, knowledge | ask_knowledge, search_kb |  |

## Answers (first repeat)

### O01: What's the difference between the Get Clássica and the Get Smart?

The main difference is that the **Get Smart** is Getnet's more complete, modern machine: it has a touchscreen, 4G and apps. The **Get Clássica** is simpler, with physical buttons, and is made from recycled material [S1][S3][S4].

| | **Get Clássica** | **Get Smart** |
|---|---|---|
| **Interface** | Physical buttons [S3] | Touchscreen with apps, such as electronic order tabs [S4][S6] |
| **Connectivity** | 3G and Wi‑Fi, with a 3G chip that includes a free data plan [S1][S3] | 3G, 4G, Wi‑Fi and Bluetooth, with a 4G chip that includes a free data plan [S1][S4] |
| **Payments** | Tap to pay (contactless), QR Code and Pix [S1] | Tap to pay (contactless), QR Code and Pix, plus chip and magnetic stripe [S1][S4] |
| **Printing** | Prints on paper rolls, and 2 rolls come in the box [S1][S3] | Prints receipts and can reprint them [S4] |
| **Extras** | None listed | Issues invoices (nota fiscal), manages sales and reports on the machine, and has a self-service kiosk mode [S1][S5][S6] |
| **Monthly fee if you miss the sales target** | R$ 79.90/month [S2] | R$ 129.90/month [S2] |

**Costs:** Either machine can be free with the best rates if you:
- open a Get Conta account
- meet the required monthly sales amount
- choose to receive payments in 2 days [S1]

If you don't reach that sales amount, you pay the monthly fee shown above [S2].

**Who it's for:** Getnet recommends the Get Smart for bars and restaurants that take payment at the table, and for street vendors because it's light and portable [S6][S7]. The sources don't say who the Get Clássica is meant for.

Getnet's information doesn't list the required sales amounts, the rate per transaction, battery life, accepted card brands or installment options. You can check these in the simulator at site.getnet.com.br/todas-as-maquininhas or in the Getnet app [S2].

### O02: What's the weather forecast in Porto Alegre tomorrow?

Tomorrow, Wednesday 18 November, Porto Alegre is expected to have **thunderstorms with possible hail** [S1].

- **Temperature:** low of 21.3 °C, high of 30.9 °C
- **Rain:** 82% chance, about 16.5 mm
- **Wind:** up to 11.5 km/h

Bring an umbrella, and if you can, keep vehicles and outdoor equipment under cover because of the hail. For live storm alerts, check Defesa Civil RS or INMET.

This forecast came from Open-Meteo at 14:59 today and could change.

[S1] Open-Meteo forecast API (https://open-meteo.com/)

### O03: When will the money from yesterday's sales be deposited?

You'll get **R$ 2.934,66 net** from yesterday's sales (Monday, 16/11), deposited on three different dates to your Conta Getnet •••• 1988:

| Type | Net amount | Deposit date | Status |
|---|---|---|---|
| Pix (2 sales) | R$ 323,94 | 16/11 (same day) | Already paid |
| Debit (7 sales) | R$ 2.055,56 | **Today, 17/11** | Scheduled |
| Credit (4 sales, all paid in full) | R$ 555,16 | 16/12/2026 | Scheduled |

Your total sales were R$ 2.984,53, and fees came to R$ 49,87.

**Two things to check:**
- **Declined sale:** A R$ 158,90 credit sale at 17:40 (Elo, card ending 4421) was declined with code 51. You won't receive any money for it.
- **Possible double charge:** Two credit sales of R$ 239,90 were made on the same Mastercard (ending 8812), one minute apart, on machine T-1988-02. Their IDs are S-1988-01225 and S-1988-01226. Please check whether the customer really made two purchases. If one was a mistake, it should be cancelled before it's paid on 16/12.

The dates and amounts above come from your current schedule and could still change, for example if a sale is cancelled.

### O04: Do I need a bank account to receive my sales via Pix?

**Yes. You need an account to receive the money, but it doesn't have to be Getnet's own account.** To receive Pix sales with Getnet, you need a receiving account that has a Pix key registered to it. Getnet pays the net amount of each Pix sale into that account [S1].

**What you need:**
- **A receiving account with a Pix key.** The key can be your CPF/CNPJ, mobile number, email or a random key. Getnet recommends a random key or your CNPJ, because the payer can see the key. A key can only be linked to one institution [S1].
- **Pix turned on with Getnet.** Do this in the Portal Minha Conta or the Getnet app, using the same key you registered at the bank that will receive the money [S1].
- **Correct bank details.** If your details don't match, the transfer is refused and the sale shows **"Falha no repasse"** (transfer failed) [S5].

**Which account you can use:**
- **Get Conta** is Getnet's free digital business account and can receive Pix. The sources don't say you must open it to receive Pix [S1].
- **A bank account at another institution** may also work. The sources say to check with Getnet which institutions are supported, but that guidance is from 2020 and may be out of date [S1].
- **Free card machine offers** (Get Smart, Get Mini, Get Clássica) do require a Get Conta. That condition is part of the machine offer, not a Pix requirement [S2].

The sources don't say whether Get Conta is required on every plan or which banks are supported today, so Getnet Customer Service would need to confirm both for your account.

### O05: My card machine won't connect to the internet, what should I do?

**The machine that's down is your Get Smart (T-1988-01).** It uses Wi-Fi and has been offline since about 12:00 today. Your Get Clássica (T-1988-02) uses its SIM chip (4G) and is online. That points to a problem with your store's Wi-Fi or the machine itself, not a wider Getnet outage. **Until it's fixed, you can take payments on the Get Clássica.**

**Steps to try on the Get Smart:**
1. **Check your internet:** make sure your Wi-Fi works on another device, such as your phone [S1].
2. **Restart:** turn the router and the Get Smart off and back on.
3. **Reconnect to Wi-Fi:** on the home screen, go to **"Configurar" → "Conexões"**. Select your network again and re-enter the password carefully [S1][S5].
4. **Test it:** in the same menu, run **"Teste de Conexão"** (connection test) [S5]. If Wi-Fi still fails, you can switch to the machine's 4G chip in that menu too [S5].
5. **If an error code appears on screen:**
   - **ADQ 1-18 or ADQ 1-84 (weak or unstable signal):** Function → 25 → operator password → Function 46, then make a test sale [S10][S11].
   - **ADQ 4-30, ADQ 4-27 or S-2074 (communication failure):** Function → 38 → "Inicialização", then make a test sale [S8][S9][S12].
   - These key sequences may vary by model.
6. **Move it closer to the router**, and check whether the network name or password changed recently.

**If it's still offline, contact Getnet:**
- **Getnet Brasil app:** go to "Manutenção de máquina", choose the terminal and the reason, or tap "iniciar chat" for WhatsApp support. You'll get a ticket number [S14].
- **Phone:** 4002-4000 / 4003-4000 in state capitals, or 0800-648-8000 elsewhere, 06h–21h [S16].
- **WhatsApp:** 11 97694-6815, 06h–21h [S16].
- **24/7 SAC line:** 0800-646-2606 [S13].

I can't see outage alerts, the machine's Wi-Fi signal strength or why it disconnected, so I can't completely rule out a wider problem.

### O06: How does receivables advance (antecipação) work with Getnet?

With Getnet, a receivables advance ("Antecipação de Vendas") pays you sales money before its normal payment date, so you don't have to wait 30, 60 or 90+ days [S1][S2]. You can request one-off advances in the Getnet Brasil app or turn on automatic advances. Either way, the minimum is R$50.00 [S6].

**Which sales qualify**
- Getnet's FAQ and app guide say credit card sales qualify, whether paid in full or in installments [S2][S6].
- A newer Getnet article also lists debit and Pix sales [S1]. Your app shows which sales you can actually advance.

**1. One-off (spot) advance in the Getnet Brasil app** [S6]
1. Go to **Serviços**, then **Antecipação de Vendas**.
2. Check how much you can advance and choose the bank account to receive it.
3. Accept the terms and run the simulation. It shows the amounts, card brands and fees.
4. Confirm, tap **Antecipar** and enter your password.
5. Track the request under **Meus Pedidos**.

**2. Automatic advance (Antecipação Automática)**
- This is a credit approval, so Getnet reviews it and may approve or decline it [S2].
- On the "Receba Conforme suas Vendas" plan, automatic advance is required to get that plan's fee exemption [S2].
- A Getnet help page found on the web gives these steps: go to **Serviços**, then **Antecipação Automática**, then **Habilitar**, enter your password and accept the terms.
  - Approval can take up to 48 hours.
  - You need an admin profile to turn it on or off.
  - Advances only run once at least R$50 is available.

**Fees**
- Advancing has its own fee, separate from your normal sales fees [S4]. The simulation shows the exact cost before you confirm [S6].
- Getnet's sources don't publish a set advance rate, so check the simulation.
- Crediário sales are different: you get the full amount within 2 business days at a single fee, with no advance cost [S5].

**When the money arrives**
- Getnet's official content doesn't say.
- An older Getnet blog post (about 5 years old) said 1 business day. Treat that only as a guide and check the date shown in the app.

**A separate product:** Getnet also offers a loan that uses your receivables as a guarantee. It's credited to your Get Conta right away, or the next business day if you sign after 6 pm [S7].

The automatic-advance steps and the 1-business-day timing come from web pages, not Getnet's official knowledge base. I can also check how much you have available to advance right now.

### O07: What's the euro exchange rate today?

Today (17/11/2026), €1 is worth about **R$ 6.3659** (sell rate) [S1].

- **Buy:** R$ 6.3647 per €1
- **Sell:** R$ 6.3659 per €1
- This is the Banco Central do Brasil's PTAX closing rate, published at 13:07 today [S1].

This is only a reference rate. Card machines (including dynamic currency conversion, or DCC), banks and exchange offices set their own rates and usually add a spread or fees, so the amount you actually pay or get will probably be different [S1].

### O08: My card machine is showing a transaction decline error.

I couldn't tell from your account data which error is on the screen right now, but I found two likely causes: one of your machines is offline, and today's declines came from the customers' card issuers.

**1. One machine is offline**
- **T-1988-01 (Get Smart, Wi-Fi):** offline since about 12:00, roughly 3 hours. It can't process card payments until it reconnects. Check your Wi-Fi and router, then restart the machine.
- **T-1988-02 (Get Clássica, 4G):** online and working. Use it until the other one reconnects.

**2. Today's declines (both Elo debit cards)**
- **09:12, T-1988-02, R$ 42,50, code 57:** this card doesn't allow this kind of transaction. Don't try again. Ask the customer to pay another way.
- **T-1988-01, R$ 416,25, code 51:** the card didn't have enough balance or limit. The customer can try again or use another card or Pix.

Most other cards went through today, including Visa and an Elo credit card. So these declines are about the customers' cards, not a fault in the machine.

**Something to check:** yesterday (16/11), Mastercard •8812 was charged R$ 239,90 twice, at 11:05 and 11:06 on T-1988-02. Please confirm whether both charges were meant to happen.

Some of the times in the records look wrong. The R$ 416,25 decline and one approved sale are logged at 19:04 and 17:10, which is later than now. Also, T-1988-01 shows activity after it went offline, so some times or statuses may be off.

**Which machine is showing the error, and what's the exact code or message on the screen?** With that I can tell you exactly what it means.

### O09: How many installments can I split a sale into with the crediário?

With Getnet Crediário, your customer can split a sale into **up to 48 installments** on a credit card [S4][S3]. That's the maximum. The customer's card issuer sets the actual limit, so some customers may be offered fewer [S4].

**How it works for you:**
- **Interest:** Your customer pays the installment interest, and the rate depends on their card issuer [S4].
- **Payment:** You get the full sale amount in one payment within 2 business days, however many installments the customer picks. Only the discount fee (MDR) is taken out [S4][S1]. There's one fee and no anticipation cost [S4].
- **Your fee:** Your Crediário rate is set in your contract. You can see it in the Getnet app or the Customer Portal [S1][S4].
- **Eligibility:** Getnet has to review and approve your business before Crediário is turned on [S4][S1].

**How to turn it on:**
1. Request it in the Getnet app or through the call center [S1].
2. Check that it's on in the app under *Meu negócio > Taxas e modalidades > Cartões*, or in the Customer Portal [S1].
3. If it's on but doesn't show on your machine, make a regular card sale or restart the machine's setup: *Suporte > Bandeiras > Funções Técnicas > Inicialização* [S1].

**Other installment options:** "Parcelado Emissor" allows up to 24 installments. "Parcelado Lojista" is interest-free for the customer and allows up to 12 [S1].

The sources I found don't list which card brands and machines support Crediário. The call center can confirm that for you.

### O10: Can I sell through WhatsApp using the Payment Link?

**Yes.** Getnet's Payment Link is built for selling online and on WhatsApp, and you don't need a website or a card machine [S1].

**How it works**
1. **Create the link** in the Getnet Brasil app or the Portal do Cliente Getnet [S1].
2. **Choose how the customer can pay:** debit, credit in one payment, credit in installments, Pix or digital wallets [S1].
3. **Send the link on WhatsApp**, or by SMS, email or any other channel you use [S1].
4. **The customer taps the link and pays** on a secure page [S2]. They don't need to install an app or create an account [S3].
5. **Track your sales** in one place, with real-time updates, reports and transaction history [S3].

**Good to know**
- Meta no longer supports payments inside WhatsApp Business. Merchants who had Getnet's old WhatsApp Business package were moved to the Payment Link package, so you sell on WhatsApp by sending a link [S1].
- If you go more than 4 months without a sale through the link, it gets turned off and you have to go through approval again [S8].
- After 6 months of use, you can ask to be paid two days after each sale (D+2). Getnet reviews each request [S8].
- All Getnet online-sales packages include the Payment Link [S8].

Getnet's information doesn't cover the link's fees, minimum or maximum amounts, maximum number of installments or how long a link stays valid. You can check those in the app, in the Portal or with Getnet support.

