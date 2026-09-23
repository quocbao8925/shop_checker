package vn.shopchecker

import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.content.res.ColorStateList
import android.view.Gravity
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.WindowManager
import android.webkit.*
import android.widget.*
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import org.json.JSONObject
import org.json.JSONArray
import java.util.UUID
import java.util.Date
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

class MainActivity : Activity() {
    private val images = SkinImages()
    private val canvasColor = Color.rgb(12, 14, 18)
    private val panel = Color.rgb(30, 33, 39)
    private val accent = Color.rgb(255, 70, 85)
    private val muted = Color.rgb(170, 174, 183)
    private var centered = true
    private val worker = Executors.newSingleThreadExecutor()
    private val cookieWorker = Executors.newSingleThreadExecutor()
    private val cookiePending = AtomicBoolean(false)
    private val requestRunning = AtomicBoolean(false)
    private val handler = Handler(Looper.getMainLooper())
    private var taskId = 0L
    private lateinit var vault: SessionVault
    private lateinit var body: LinearLayout
    private var browser: WebView? = null
    private var loginState: String? = null
    private var busy = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.statusBarColor = canvasColor
        window.navigationBarColor = canvasColor
        vault = SessionVault(this)
        refresh()
    }
    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()
    private fun shape(color: Int, stroke: Int = color) = GradientDrawable().apply {
        setColor(color); cornerRadius = dp(12).toFloat(); setStroke(dp(1), stroke)
    }
    private fun page(title: String, center: Boolean = true, brandOnly: Boolean = false) {
        centered = center
        body = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = if (center) Gravity.CENTER_VERTICAL else Gravity.TOP
            setPadding(dp(20), dp(24), dp(20), dp(24))
        }
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(canvasColor)
        }
        val scroll = ScrollView(this).apply {
            isFillViewport = true
            clipToPadding = false
            addView(body, android.view.ViewGroup.LayoutParams(-1, -2))
        }
        root.addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f))
        if (brandOnly) root.addView(footer())
        setContentView(root)
        if (brandOnly) label("SHOP CHECKER", 38f, accent)
        else {
            label("SHOP CHECKER", 18f, accent)
            label(title, 28f)
        }
    }
    private fun footer(): LinearLayout {
        val version = packageManager.getPackageInfo(packageName, 0).versionName ?: ""
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(dp(16), dp(8), dp(16), dp(18))
            addView(text("v$version", 11f, muted).apply { gravity = Gravity.CENTER })
            addView(text("github.com/quocbao8925/shop_checker", 11f, muted).apply {
                gravity = Gravity.CENTER
                minHeight = dp(48)
                setOnClickListener {
                    try {
                        startActivity(Intent(Intent.ACTION_VIEW,
                            Uri.parse("https://github.com/quocbao8925/shop_checker")))
                    } catch (_: android.content.ActivityNotFoundException) {
                        Toast.makeText(this@MainActivity, "No browser available.", Toast.LENGTH_SHORT).show()
                    }
                }
            })
        }
    }
    private fun text(value: String, size: Float, color: Int = Color.WHITE) =
        TextView(this).apply {
            text = value; textSize = size; setTextColor(color)
            setPadding(0, dp(6), 0, dp(6))
            if (size >= 22f) typeface = Typeface.DEFAULT_BOLD
        }
    private fun label(value: String, size: Float = 16f, color: Int = Color.WHITE) {
        body.addView(text(value, size, color).apply {
            gravity = if (centered) Gravity.CENTER else Gravity.START
        })
    }
    private fun button(title: String, primary: Boolean = false, action: () -> Unit) {
        body.addView(Button(this).apply {
            text = title; isAllCaps = true; setTextColor(Color.WHITE)
            typeface = Typeface.DEFAULT_BOLD
            background = shape(if (primary) accent else panel)
            layoutParams = LinearLayout.LayoutParams(-1, dp(52)).apply { topMargin = dp(12) }
            setOnClickListener { action() }
        })
    }
    private fun offerCard(offer: JSONObject): LinearLayout {
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(12), dp(12), dp(12), dp(12))
            background = GradientDrawable(
                GradientDrawable.Orientation.TL_BR,
                intArrayOf(Color.rgb(77, 26, 37), panel, Color.rgb(19, 21, 26))
            ).apply { cornerRadius = dp(12).toFloat(); setStroke(dp(1), Color.rgb(90, 43, 51)) }
            artwork(this, offer.optString("display_icon"), offer.optString("name"), 110)
            addView(text(offer.optString("name", "Unknown skin"), 17f).apply {
                typeface = Typeface.DEFAULT_BOLD
                minLines = 2
            })
            val kind = offer.optString("kind", offer.optString("content_tier_name"))
            if (kind.isNotBlank()) addView(text(kind, 12f, muted))
            val cost = offer.optInt("cost")
            val price = offer.optString("price_label", if (cost > 0) "$cost VP" else "")
            if (price.isNotBlank()) addView(text(price, 18f, accent))
            val discount = offer.optDouble("discount_percent", 0.0)
            if (discount > 0) {
                val percent = if (discount < 1) discount * 100 else discount
                addView(text("${percent.toInt()}% OFF", 12f, accent))
            }
        }
    }
    private fun artwork(parent: LinearLayout, url: String, name: String, height: Int) {
        // Missing artwork is intentional: keep the item name without an error placeholder.
        if (url.isBlank() || url == "null") return
        val image = ImageView(this).apply {
            scaleType = ImageView.ScaleType.FIT_CENTER
            contentDescription = name
            setPadding(dp(4), dp(8), dp(4), dp(8))
        }
        parent.addView(image, LinearLayout.LayoutParams(-1, dp(height)))
        images.load(url) { bitmap ->
            if (!isDestroyed) {
                if (bitmap != null) image.setImageBitmap(bitmap)
                else image.visibility = android.view.View.GONE
            }
        }
    }
    private fun itemGrid(items: JSONArray) {
        for (i in 0 until items.length() step 2) {
            val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            for (j in i..i + 1) {
                val card = if (j < items.length()) offerCard(items.getJSONObject(j)) else LinearLayout(this)
                row.addView(card, LinearLayout.LayoutParams(0, -1, 1f).apply {
                    if (j > i) leftMargin = dp(12)
                })
            }
            body.addView(row, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(12) })
        }
    }
    private fun resetLabel(seconds: Long, fetched: Double) {
        val remaining = (fetched + seconds - System.currentTimeMillis() / 1000).toLong().coerceAtLeast(0)
        val days = remaining / 86400
        label("Resets in " + (if (days > 0) "${days}d " else "") +
            "${remaining % 86400 / 3600}h ${remaining % 3600 / 60}m", 13f, muted)
    }
    private fun call(name: String, vararg args: Any): String {
        if (!Python.isStarted()) Python.start(AndroidPlatform(applicationContext))
        return Python.getInstance().getModule("android_bridge").callAttr(name, *args).toString()
    }
    private fun task(message: String, work: () -> String, timeoutMs: Long = 90000L, done: (String) -> Unit) {
        if (busy) return
        if (!requestRunning.compareAndSet(false, true)) {
            welcome("The previous request is still finishing. Please retry shortly, or reopen the app. [REQUEST_BUSY]")
            return
        }
        val id = ++taskId
        busy = true
        page("SHOP CHECKER", brandOnly = true)
        label(message, 14f, muted)
        body.addView(ProgressBar(this).apply {
            indeterminateTintList = ColorStateList.valueOf(accent)
            layoutParams = LinearLayout.LayoutParams(dp(40), dp(40)).apply { gravity = Gravity.CENTER; topMargin = dp(20) }
        })
        val timeout = Runnable {
            if (!isDestroyed && id == taskId) {
                ++taskId
                busy = false
                welcome("Request timed out: $message Please try again. [REQUEST_TIMEOUT]")
            }
        }
        handler.postDelayed(timeout, timeoutMs)
        button("Cancel") {
            ++taskId
            handler.removeCallbacks(timeout)
            busy = false
            welcome()
        }
        worker.execute {
            // Cancellation invalidates the UI result; it cannot forcibly stop Python I/O.
            val result = try { work() } catch (_: Exception) { null }
            requestRunning.set(false)
            handler.post {
                handler.removeCallbacks(timeout)
                if (!isDestroyed && id == taskId) {
                    busy = false
                    try {
                        if (result == null) welcome("Unable to complete: $message Please retry. [REQUEST_FAILED]")
                        else done(result)
                    } catch (_: Exception) {
                        // Never expose raw Python errors, callback URLs or tokens.
                        welcome("Unable to read the server response. Please retry. [RESPONSE_FAILED]")
                    }
                }
            }
        }
    }
    private fun welcome(message: String = "") {
        page("SHOP CHECKER", brandOnly = true)
        if (message.isNotBlank()) label(message, 15f, muted)
        button("Sign in with Riot", primary = true) { beginLogin() }
        val session = vault.load()
        val authenticated = try {
            val token = session?.let { JSONObject(it) }
            token != null && token.optDouble("created_at") + token.optDouble("expires_in") >
                System.currentTimeMillis() / 1000
        } catch (_: Exception) { false }
        if (authenticated) {
            button("Try loading shop") { refresh() }
            button("Sign out") { logout() }
        }
        label("Unofficial companion. Not endorsed by Riot Games.", 11f, muted)
    }
    private fun refresh(allowRenewal: Boolean = true) {
        task("Loading your shop...", {
            val session = vault.load()
            if (session == null) "{\"status\":\"login_required\"}"
            else call("shop", filesDir.absolutePath, session)
        }) { renderShop(JSONObject(it), allowRenewal) }
    }
    private fun errorCode(result: JSONObject): String = result.optString("code")
        .takeIf { it.matches(Regex("(AUTH|STORE|SHOP)_(HTTP_[0-9]{3}|NETWORK|FAILED)")) }
        ?: "REQUEST_FAILED"
    private fun renderShop(result: JSONObject, allowRenewal: Boolean = true) {
        val status = result.getString("status")
        if (status == "login_required") {
            // Expiry is not logout: retain the session marker and Riot's cookies.
            // One renewal per refresh prevents loops if newly issued tokens are rejected.
            if (allowRenewal && vault.load() != null) beginLogin(renewing = true)
            else welcome(if (vault.load() != null) "Please sign in to continue." else "")
            return
        }
        if (status == "unavailable") {
            welcome("Your shop is unavailable. Please try again later. [${errorCode(result)}]")
            return
        }
        val snapshot = result.getJSONObject("snapshot")
        page("YOUR SHOP", center = false)
        val fetched = snapshot.getDouble("fetched_at")
        label(if (status == "cached") "CACHED STORE | ${Date((fetched * 1000).toLong())}" else "LIVE STORE")
        if (status == "cached") label("Live update failed. [${errorCode(result)}]", 13f, muted)
        val wallet = snapshot.getJSONObject("wallet")
        label("${wallet.getInt("valorant_points")} VP   |   ${wallet.getInt("radianite_points")} RP   |   ${wallet.optInt("kingdom_credits")} KC")
        label("DAILY SHOP", 22f)
        val daily = snapshot.getJSONObject("daily_store")
        resetLabel(daily.getLong("seconds_remaining"), fetched)
        val offers = daily.getJSONArray("offers")
        if (offers.length() == 0) label("No offers available.", 14f, muted)
        itemGrid(offers)
        val bundles = snapshot.getJSONArray("bundles")
        if (bundles.length() > 0) label("FEATURED BUNDLES", 22f)
        for (i in 0 until bundles.length()) {
            val bundle = bundles.getJSONObject(i)
            label(bundle.getString("name"), 24f)
            label("${bundle.getInt("total_discounted_price")} VP", 18f, accent)
            resetLabel(bundle.optLong("duration_remaining_secs"), fetched)
            artwork(body, bundle.optString("display_icon"), bundle.getString("name"), 160)
            val items = bundle.optJSONArray("items") ?: JSONArray()
            val cards = JSONArray()
            for (j in 0 until items.length()) {
                val item = items.getJSONObject(j)
                val cost = item.optInt("discounted_price")
                cards.put(JSONObject(item.toString())
                    .put("price_label", if (cost > 0) "$cost VP" else "Included")
                    .put("kind", "Bundle item"))
            }
            itemGrid(cards)
        }
        val sections = snapshot.optJSONArray("sections") ?: JSONArray()
        var hasAccessories = false
        for (i in 0 until sections.length()) {
            val section = sections.getJSONObject(i)
            val name = section.getString("name")
            if (name == "ACCESSORIES") hasAccessories = true
            val items = section.optJSONArray("items") ?: JSONArray()
            if (items.length() == 0 && name != "ACCESSORIES") continue
            label(name, 22f)
            if (name == "ACCESSORIES") label("Prices in Kingdom Credits (KC)", 13f, muted)
            if (!section.isNull("seconds_remaining")) {
                resetLabel(section.getLong("seconds_remaining"), fetched)
            }
            if (items.length() == 0) label("No offers available.", 14f, muted)
            itemGrid(items)
        }
        if (!hasAccessories) {
            label("ACCESSORIES", 22f)
            label("Accessory offers are not available in this snapshot.", 14f, muted)
        }
        button("Refresh shop", primary = true) { refresh() }
        button("Sign out") { logout() }
    }
    private fun beginLogin(renewing: Boolean = false) {
        if (busy || browser != null) return
        val state = UUID.randomUUID().toString()
        loginState = state
        task(if (renewing) "Restoring your Riot session..." else "Opening Riot sign-in...", { call("login_url", state) }) { url ->
            page("RIOT SIGN IN", center = false)
            window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
            button("Cancel sign-in") { closeBrowser(); welcome() }
            val web = WebView(this)
            browser = web
            web.settings.javaScriptEnabled = true
            web.settings.domStorageEnabled = true
            web.settings.allowFileAccess = false
            web.settings.allowContentAccess = false
            web.settings.mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            CookieManager.getInstance().setAcceptCookie(true)
            CookieManager.getInstance().setAcceptThirdPartyCookies(web, false)
            web.webViewClient = object : WebViewClient() {
                override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                    if (view !== browser) return true
                    val value = request.url.toString()
                    if (request.isForMainFrame && capture(value)) return true
                    return request.url.scheme != "https"
                }
                override fun doUpdateVisitedHistory(view: WebView, url: String, reload: Boolean) {
                    if (view === browser) capture(url)
                }
                override fun onPageFinished(view: WebView, url: String) {
                    if (view === browser) {
                        persistCookies()
                        capture(url)
                    }
                }
                override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                    if (view === browser && request.isForMainFrame && !capture(request.url.toString()) && browser != null) {
                        closeBrowser(); welcome("Unable to open Riot. Check your connection and try again.")
                    }
                }
            }
            body.addView(web, LinearLayout.LayoutParams(-1, (resources.displayMetrics.heightPixels * 0.72).toInt()))
            web.loadUrl(url)
        }
    }
    private fun capture(url: String): Boolean {
        val uri = Uri.parse(url)
        if (uri.scheme != "http" || uri.host != "localhost" || uri.port != -1 || uri.path != "/redirect") return false
        val state = loginState ?: return true
        loginState = null
        persistCookies()
        closeBrowser()
        task("Connecting to your Riot account...", {
            call("authenticate_result", url, state)
        }, timeoutMs = 50000L) {
            val result = JSONObject(it)
            if (result.optString("status") == "authenticated") {
                // Only a current, non-cancelled login may change the saved account.
                vault.save(result.getJSONObject("session").toString())
                refresh(allowRenewal = false)
            } else welcome("Unable to connect to your Riot account. Please retry. [${errorCode(result)}]")
        }
        return true
    }
    private fun closeBrowser() {
        loginState = null
        browser?.let { web ->
            web.stopLoading()
            (web.parent as? android.view.ViewGroup)?.removeView(web)
            web.destroy()
        }
        browser = null
        window.clearFlags(WindowManager.LayoutParams.FLAG_SECURE)
    }
    private fun logout() {
        if (busy) return
        closeBrowser()
        vault.clear()
        busy = true
        page("SHOP CHECKER", brandOnly = true)
        label("Signing out...", 14f, muted)
        // Do not allow a new sign-in while old cookies are still being removed.
        CookieManager.getInstance().removeAllCookies {
            CookieManager.getInstance().flush()
            WebStorage.getInstance().deleteAllData()
            busy = false
            if (!isDestroyed) welcome()
        }
    }
    @Deprecated("Legacy Activity navigation")
    override fun onBackPressed() {
        if (browser != null) { closeBrowser(); welcome() }
        else if (!busy) super.onBackPressed()
    }
    private fun persistCookies() {
        if (!cookieWorker.isShutdown && cookiePending.compareAndSet(false, true)) {
            cookieWorker.execute {
                try { CookieManager.getInstance().flush() }
                catch (_: Exception) { /* Retain cookies in memory; never force logout. */ }
                finally { cookiePending.set(false) }
            }
        }
    }
    override fun onPause() {
        persistCookies()
        super.onPause()
    }
    override fun onDestroy() {
        ++taskId
        handler.removeCallbacksAndMessages(null)
        closeBrowser()
        images.close()
        worker.shutdown()
        cookieWorker.shutdown()
        super.onDestroy()
    }
}
