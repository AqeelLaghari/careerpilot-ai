# Hosting guide: keep the backend running, renew it, or move it

This guide covers everything needed to keep CareerPilot AI online until (and after) the defense,
without help. Every step uses **Windows PowerShell** on the laptop that has the repo.

## 1. How the pieces fit together

| Piece | Where it runs | Cost | What decides its address |
|---|---|---|---|
| Website (Flutter web) | Firebase Hosting: https://careerpilot-ai-762bb.web.app (+ your own domain) | free forever | Firebase |
| Backend (FastAPI, AI models) | Azure Container Apps (Azure for Students credit) | from the $100 student credit | Azure |
| Database + login | Firebase (Firestore + Auth) | free forever | Firebase |
| Android app | the phone | free | reads the backend address from the website |

**The one switch:** the website and the Android app both read the backend address from
[`frontend/web/config.json`](../frontend/web/config.json) on the website:

```json
{"api_url": "https://careerpilot-api.wittypebble-6c0ea672.uaenorth.azurecontainerapps.io"}
```

To move the backend anywhere, only this line changes, and **the scripts change it for you** (they push it on
a new branch and print the pull request link). The GitHub workflows read the address from this file too. You
do **not** rebuild the APK, and the domain does not change (it points to the website, not to the backend).

**The three scripts** (in `deploy\`, run from the repo folder in PowerShell):

| Script | What it does |
|---|---|
| `azure-setup.ps1` | builds the whole backend on the Azure account you are logged in to, copies the keys, gives GitHub deploy access, switches the website + app to it |
| `laptop-server.ps1` | runs the backend on this laptop with a free public tunnel, switches the website + app to it |
| `set-backend-url.ps1 <address>` | only switches the website + app to an address (e.g. back to Azure) |

**Files that are never in GitHub** (keep a copy on a USB drive or Google Drive):

- `backend/.env` (Gemini key, YouTube key, admin IDs)
- `backend/firebase-key.json` (Firebase admin key)
- the Android signing key folder `CareerPilot AI Keys` (only needed to publish a new APK)

## 2. Everyday use

### Wake the server before a demo
The server sleeps when nobody uses it (that is what keeps it almost free). The first visit wakes it in about
5-60 seconds. Before a demo:

1. **Easiest:** open https://careerpilot-ai-762bb.web.app about **5 minutes before** and log in. Done.
2. **Defense day (no waiting at all):** GitHub → repo → **Actions** → **Uptime** → **Run workflow** →
   mode **awake** → **Run workflow**. Wait for the green tick (2-3 minutes).
   - It costs about $1.50 a day while awake. **Every night at 02:00 it automatically goes back to sleep**, so
     forgetting it costs at most one day.
   - To stop it by hand: the same steps with mode **sleep**.
3. **Is it working?** Open `<server address>/health` in a browser. You should see
   `"status":"ok"`, `"firestore_connected":true` and `"gemini_key_set":true`.

### Check the student credit
1. https://portal.azure.com → search **Education** → **Overview**: credit left + days until it expires.
2. To see *what* costs money: search **Cost Management** → **Cost analysis** → group by **Resource**.
   Only `careerpilot-api` should cost money. Delete or stop anything else you don't need
   (an old web app on a "Basic B1" plan costs about $13 a month even if nobody uses it).

### What it costs
- The first **~25 hours of active use per month are free**, then about **$0.22 per active hour**.
  "Active" means somebody is using it; the server sleeps after ~5 quiet minutes and then costs nothing.
- A pilot test with 10 people is about $1-3. A month of normal testing is about $2-8.
- So the money ($100) is not the problem; **the end date is**: the student credit **expires on 12 Feb 2027**.
  Before that date choose option A, B or C below.

## 3. What happens on 12 February 2027

Azure for Students ends after 12 months (or earlier if the $100 is used up). Then the subscription is
**disabled**: the server stops, `/health` stops answering, and the website shows "cannot reach the server".
The website, the logins and all the data (Firestore) are **not** affected: they are on Firebase.

Paying Azure a few dollars to continue is **not possible without a credit/debit card** (Azure requires a card
to switch to "pay as you go"). So the three card-free options are:

| | Option | Effort | When |
|---|---|---|---|
| **A** | Renew your own Azure for Students | 5 minutes | on/after 12 Feb 2027, if you are still a student |
| **B** | Move to a teammate's Azure for Students | 20-30 minutes | any time (best done a week before the defense) |
| **C** | Run the backend on the laptop + Cloudflare Tunnel | 10 minutes | emergency / defense day backup |

Start with A. If renewal is refused, do B. Keep C as the backup for the defense itself.

## 4. Option A: renew your Azure for Students

1. Around 12 Feb 2027 Microsoft emails a renewal reminder. Open https://azure.microsoft.com/free/students
   (or portal.azure.com → **Education**) and sign in with **the same account** as now.
2. Click **Renew** (or **Start free** / **Activate**) and verify with the university email if asked. No card.
3. Check portal.azure.com → **Subscriptions**:
   - **"Azure for Students" is Active again (same name, same ID):** nothing else to do. Open
     `<server address>/health` to confirm (wait a minute for it to wake up).
   - **You got a new subscription with a different ID:** the old server is gone with the old subscription.
     Do **option B steps B2-B7** with your own login. That rebuilds everything in 20 minutes.
4. If it says you are not eligible: do option B with a teammate.

## 5. Option B: move to another Azure account (teammate's)

### B1. Teammate activates Azure for Students (5 minutes, no card)
The teammate opens https://azure.microsoft.com/free/students → **Start free** → signs in with a Microsoft
account → verifies with their **university email**. They don't need to do anything else.

### B2. Install the Azure CLI (only if this laptop doesn't have it)
```powershell
winget install -e --id Microsoft.AzureCLI
```
Close PowerShell and open it again. Check: `az version` prints a version number.

### B3. Sign in with the teammate's account
The teammate sits with you (or gives you their login for 10 minutes):
```powershell
az logout
az login
```
A browser opens → sign in with the teammate's account → back in PowerShell, if it asks
"Select a subscription", type the number next to **Azure for Students** and press Enter.

### B4. Run the setup script (10-15 minutes)
```powershell
cd "C:\Users\Hp\Documents\CareerPilot AI"
git switch main
git pull
powershell -ExecutionPolicy Bypass -File deploy\azure-setup.ps1
```
- It shows the subscription and asks `Create the CareerPilot backend in THIS subscription? (y/n)` → type `y`.
- It reads `backend\.env` and `backend\firebase-key.json` (they must be in the backend folder) and saves them
  as Azure secrets. Nothing secret is printed.
- If it stops with "does not allow region 'uaenorth'": run it again with `-Location centralindia`.
- At the end it prints a **DONE** box with **3 IDs**, then pushes the new address on a new branch and prints
  **LAST STEP** with a pull request link. Keep the window open.

### B5. Paste the 3 IDs into GitHub (only the repo owner can do this)
GitHub → repo → **Settings** → **Secrets and variables** → **Actions** → for each of these three click the
pencil (**Update**), paste the value from the DONE box, **Update secret**:
- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`

### B6. Merge the address change
Open the **LAST STEP** link → **Create pull request** → wait for green → **Squash and merge** →
**Delete branch**. About 5 minutes later the **Web** action has published it. Open the website, press
**Ctrl+F5**, log in, use a page that needs the server (e.g. upload a CV). Phones: close the app fully and
reopen it.

### B7. Check
GitHub → **Actions** → **Uptime** → **Run workflow** (mode **check**) → green tick = the new server works
and GitHub can reach it. The old account needs nothing: when it is disabled its server simply disappears.

## 6. Option C: run the backend on the laptop (Cloudflare Tunnel, free, no account)

Use this if Azure is not available, or as a backup on defense day. The laptop must stay **on, plugged in and
connected to the internet** the whole time, with sleep turned off (Settings → System → Power → Never).

### C1. Start it (one command)
```powershell
cd "C:\Users\Hp\Documents\CareerPilot AI"
git switch main
git pull
powershell -ExecutionPolicy Bypass -File deploy\laptop-server.ps1
```
- The first time it installs **cloudflared** (Cloudflare's free tunnel tool).
- It opens **two windows** (backend + tunnel). **Leave both open**; closing either stops the server.
- It waits until the public address (`https://some-words.trycloudflare.com`) answers, then prints
  **LAST STEP** with a pull request link: open it → **Create pull request** → green → **Squash and merge**.
- **The address changes every time**, so run it on the day you need it (e.g. the morning of the defense).

### C2. Stop it / go back to Azure
- Stop: close the two windows.
- Back to Azure: `powershell -ExecutionPolicy Bypass -File deploy\set-backend-url.ps1 <Azure address>` →
  merge its pull request. (The Azure address: Azure portal → **careerpilot-api** → **Application Url**.)

### C3. While running from the laptop
The **Docker** deploy and the nightly **Uptime** check still talk to Azure and fail if Azure is gone (GitHub
emails you). To silence them: GitHub → **Actions** → **Uptime** → **...** (top right) → **Disable workflow**;
the same for **Docker**. Turn them on again (**Enable workflow**) when you are back on Azure.

## 7. Your own domain (careerpilot.tech)

The domain belongs to the **website** (Firebase Hosting), never to the backend, so moving the backend
(options A-C) does not touch it.

### Connect it (one time)
1. https://console.firebase.google.com → project **careerpilot-ai-762bb** → **Hosting** → **Add custom
   domain** → type `careerpilot.tech` → **Continue**. Firebase shows the DNS records (a **TXT** and one or two
   **A** records). Keep the page open.
2. At the domain company's website → your domain → **Manage DNS / DNS records**:
   - delete the default records for host `@` (or blank) and `*` (parking page),
   - add each record exactly as Firebase shows it (host `careerpilot.tech` = `@` or blank).
3. Back in Firebase → **Verify**. "Connected" usually within minutes to a few hours (max 24 h); the https
   certificate follows by itself.
4. Optional: **Add custom domain** again with `www.careerpilot.tech` → **Redirect** to `careerpilot.tech`,
   and add the record it shows.
5. **Allow login on it:** Firebase → **Authentication** → **Settings** → **Authorized domains** → **Add
   domain** → `careerpilot.tech` (and `www.careerpilot.tech`). Without this, login fails on the new domain.

### Renewal
The free domain is valid for 1 year from the day you registered it (the "Expires on" date on the domain
company's page). Renewing costs money; if it is not renewed it simply stops, and
https://careerpilot-ai-762bb.web.app keeps working.

### If you ever move the website to another Firebase project
Remove the domain from the old project (Hosting → the domain → **Delete**), add it to the new one, and update
the DNS records to what the new project shows.

## 8. Problems and fixes

| What you see | Cause | Fix |
|---|---|---|
| Website says it cannot reach the server | server waking up | wait 1 minute, reload |
| …still after 2 minutes | Azure subscription disabled (credit ended/expired) | portal.azure.com → Subscriptions → status. Then option A, B or C |
| `/health` shows `"firestore_connected":false` | Firebase key secret wrong | run `deploy\azure-setup.ps1` again (it rewrites the secrets from `backend\`) |
| `/health` shows `"gemini_key_set":false` | Gemini key missing | put `GEMINI_API_KEY=...` in `backend\.env`, run the script again |
| Docker action fails at "azure/login" (`AADSTS700213` / no matching federated identity) | GitHub not trusted by this Azure account | run the script again, then check the 3 secrets (B5) |
| Docker action fails at "Switch the Container App" (`ResourceNotFound`) | names differ from the workflows | the app must be `careerpilot-api` in `careerpilot-rg` (the script's defaults) |
| Script stops: "does not allow region" | student account region limits | `-Location centralindia` (or `polandcentral`, `southeastasia`, `austriaeast`) |
| Login fails only on careerpilot.tech | domain not authorized | section 7 step 5 |
| Website still uses the old server after B6 | old copy in the browser | Ctrl+F5; phone: close and reopen the app |
| Interviews feel slow / cut off with many users | one server copy, 2 CPUs | ask testers to take turns (about 3-5 live interviews at once) |

**Server logs** (what the backend printed), for the Azure server:
```powershell
az containerapp logs show -n careerpilot-api -g careerpilot-rg --tail 100
```

## 9. Publishing a new Android version (only if the app code changes)

1. Write the release notes in `.github/release-notes/v1.1.1.md` (copy the previous file), merge it with the
   code change.
2. Then on `main`:
   ```powershell
   git switch main
   git pull
   git tag v1.1.1
   git push origin v1.1.1
   ```
3. GitHub → **Actions** → **Android** builds it (about 10 minutes) and publishes
   **Releases → v1.1.1** with the APK. Phones with the old version install it over the top.
