# Render.com Deployment Guide 🚀

## Prerequisites
- GitHub account
- Render.com account (free)
- Your Telegram bot token and chat ID (optional)

## Step-by-Step Deployment

### 1️⃣ Prepare Your Code

**Option A - If you have Git installed:**
```bash
cd C:\Users\T2\Desktop\Tool
git init
git add .
git commit -m "Initial commit - XAUUSD Trading Signal Tool"
```

Then create a new repository on GitHub and push:
```bash
git remote add origin https://github.com/YOUR_USERNAME/xauusd-signal-tool.git
git branch -M main
git push -u origin main
```

**Option B - Upload directly to GitHub:**
1. Go to github.com
2. Click "New repository"
3. Name it: `xauusd-signal-tool`
4. Click "uploading an existing file"
5. Drag and drop all files from `C:\Users\T2\Desktop\Tool`
6. Commit

### 2️⃣ Deploy to Render

1. **Go to [dashboard.render.com](https://dashboard.render.com)**

2. **Click "New +"** → **"Web Service"**

3. **Connect your GitHub repository:**
   - Click "Connect account" if first time
   - Select your `xauusd-signal-tool` repository
   - Click "Connect"

4. **Render will auto-configure** from `render.yaml`:
   - ✅ Name: `xauusd-alpha-bot`
   - ✅ Environment: `Python 3.11`
   - ✅ Build Command: `pip install -r requirements.txt`
   - ✅ Start Command: `uvicorn app:app --host=0.0.0.0 --port=10000`
   - ✅ Plan: `Free`

5. **Add Environment Variables** (in the Render dashboard):
   
   Scroll to **Environment Variables** section and add:
   
   | Key | Value | Example |
   |-----|-------|---------|
   | `TG_TOKEN` | Your bot token | `6234567890:ABCdefGHI...` |
   | `TG_CHAT` | Your chat ID | `123456789` |

   **Note:** These are OPTIONAL. The tool works without them!

6. **Click "Create Web Service"**

7. **Wait for deployment** (2-3 minutes)
   - You'll see build logs
   - Wait for "Your service is live 🎉"

### 3️⃣ Test Your Deployment

Your service will be available at:
```
https://xauusd-alpha-bot.onrender.com/run-signal
```

**Test in browser:**
- Just visit the URL above
- You should see JSON response with signal data

**Test with curl:**
```bash
curl https://xauusd-alpha-bot.onrender.com/run-signal
```

**Expected responses:**
```json
// BUY Signal
{
  "action": "BUY",
  "entry": 2650.50,
  "sl": 2645.30,
  "tp": 2660.90,
  "timeframe": "5m"
}

// SELL Signal  
{
  "action": "SELL",
  "entry": 2650.50,
  "sl": 2655.70,
  "tp": 2639.90,
  "timeframe": "5m"
}

// No Trade
{
  "action": "NO_TRADE",
  "reason": "HTF mismatch or neutral"
}
```

### 4️⃣ Set Up Automatic Checks (Optional)

**Option A - Use cron-job.org (Free):**
1. Go to [cron-job.org](https://cron-job.org)
2. Create free account
3. Create new cron job:
   - URL: `https://xauusd-alpha-bot.onrender.com/run-signal`
   - Interval: Every 5 minutes
   - Save

**Option B - Use Render Cron Job:**
1. In Render dashboard
2. Create New → Cron Job
3. Command: `curl https://xauusd-alpha-bot.onrender.com/run-signal`
4. Schedule: `*/5 * * * *` (every 5 minutes)

**Option C - Use UptimeRobot (Free):**
1. Go to [uptimerobot.com](https://uptimerobot.com)
2. Add new monitor
3. Type: HTTP(s)
4. URL: `https://xauusd-alpha-bot.onrender.com/run-signal`
5. Interval: 5 minutes

## 🎯 Important Notes

### Free Tier Limitations
- Render free tier **spins down after 15 minutes of inactivity**
- First request after sleep takes ~30 seconds to wake up
- Solution: Use a cron job to ping it every 5-10 minutes
- Or upgrade to paid plan ($7/month) for always-on

### Environment Variables are Secure
- ✅ Your `TG_TOKEN` and `TG_CHAT` are encrypted
- ✅ Not visible in logs or public
- ✅ Only your service can access them

### Updating Your Service
When you push new code to GitHub:
```bash
git add .
git commit -m "Updated trading logic"
git push
```
Render will **automatically redeploy**! 🎉

## 📊 Monitoring

**View Logs:**
1. Go to your service in Render dashboard
2. Click "Logs" tab
3. You'll see:
   ```
   ✓ Using cached data (1234 rows)
   ✓ Telegram message sent successfully
   ```

**Check Metrics:**
- Render dashboard shows CPU, memory usage
- Request counts and response times

## 🔒 Security Best Practices

✅ **DO:**
- Keep your `TG_TOKEN` secret
- Use environment variables (never hardcode)
- Regularly rotate your bot token

❌ **DON'T:**
- Commit tokens to GitHub
- Share your token publicly
- Use the same token for multiple projects

## 🐛 Troubleshooting

### "Build Failed"
- Check build logs in Render
- Usually missing dependencies
- Verify `requirements.txt` is correct

### "Service Unavailable"
- Free tier might be sleeping
- Wait 30 seconds for it to wake up
- Or set up a keep-alive cron job

### "Telegram Not Working"
- Check environment variables in Render dashboard
- Make sure `TG_TOKEN` and `TG_CHAT` are set correctly
- Test with the URL directly in browser first

### "No Data" or Errors
- Check logs in Render dashboard
- Yahoo Finance might be temporarily down
- Try again in a few minutes

## 🎉 You're Live!

Your trading signal tool is now:
- ✅ Running 24/7 in the cloud
- ✅ Accessible via HTTPS
- ✅ Sending Telegram alerts automatically
- ✅ Free (on Render free tier)

**Share your URL:**
```
https://xauusd-alpha-bot.onrender.com/run-signal
```

Anyone can access the signals (but only YOU get Telegram alerts!)

---

**Need help?** Check Render's documentation or your service logs!
