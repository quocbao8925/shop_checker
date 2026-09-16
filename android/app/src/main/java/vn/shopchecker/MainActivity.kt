package vn.shopchecker

import android.app.Activity
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.content.res.ColorStateList
import android.view.Gravity
import android.net.Uri
import android.os.Bundle
import android.view.WindowManager
import android.webkit.*
import android.widget.*
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import org.json.JSONObject
import java.util.UUID
import java.util.Date
import java.util.concurrent.Executors

class MainActivity : Activity() {
    private val images = SkinImages()
    private val canvasColor = Color.rgb(12, 14, 18)
    private val panel = Color.rgb(30, 33, 39)
    private val accent = Color.rgb(255, 70, 85)
    private val muted = Color.rgb(170, 174, 183)
    private var centered = true
    private val worker = Executors.newSingleThreadExecutor()
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
    private fun page(title: String, center: Boolean = true) {
        centered = center
        body = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = if (center) Gravity.CENTER_VERTICAL else Gravity.TOP
            setPadding(dp(20), dp(24), dp(20), dp(24))
        }
        setContentView(ScrollView(this).apply {
            isFillViewport = true
            setBackgroundColor(canvasColor)
            clipToPadding = false
            addView(body, android.view.ViewGroup.LayoutParams(-1, -2))
        })
        label("SHOP CHECKER", 12f, accent)
        label(title, 28f)
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
            val frame = FrameLayout(this@MainActivity)
            val placeholder = text("Loading image...", 12f, muted).apply { gravity = Gravity.CENTER }
            val image = ImageView(this@MainActivity).apply {
                scaleType = ImageView.ScaleType.FIT_CENTER
                contentDescription = offer.optString("name", "Weapon skin")
                setPadding(dp(4), dp(8), dp(4), dp(8))
            }
            frame.addView(placeholder, FrameLayout.LayoutParams(-1, -1))
            frame.addView(image, FrameLayout.LayoutParams(-1, -1))
            addView(frame, LinearLayout.LayoutParams(-1, dp(110)))
            images.load(offer.optString("display_icon")) { bitmap ->
                if (!isDestroyed) {
                    if (bitmap != null) { image.setImageBitmap(bitmap); placeholder.visibility = android.view.View.GONE }
                    else placeholder.text = "Image unavailable"
                }
            }
            addView(text(offer.optString("name", "Unknown skin"), 17f).apply {
                typeface = Typeface.DEFAULT_BOLD
                minLines = 2
            })
            addView(text(offer.optString("content_tier_name", "Unknown"), 12f, muted))
            val cost = offer.optInt("cost")
            addView(text(if (cost > 0) "$cost VP" else "Price unavailable", 18f, accent))
        }
    }
    private fun call(name: String, vararg args: Any): String {
        if (!Python.isStarted()) Python.start(AndroidPlatform(applicationContext))
        return Python.getInstance().getModule("android_bridge").callAttr(name, *args).toString()
    }
    private fun task(message: String, work: () -> String, done: (String) -> Unit) {
        if (busy) return
        busy = true
        page(message)
        body.addView(ProgressBar(this).apply {
            indeterminateTintList = ColorStateList.valueOf(accent)
            layoutParams = LinearLayout.LayoutParams(dp(40), dp(40)).apply { gravity = Gravity.CENTER; topMargin = dp(20) }
        })
        worker.execute {
            try {
                val result = work()
                runOnUiThread { busy = false; if (!isDestroyed) done(result) }
            } catch (_: Exception) {
                // Never expose a Python exception: it can contain account data or tokens.
                runOnUiThread {
                    busy = false
                    if (!isDestroyed) welcome("Unable to connect. Check your connection and try signing in again.")
                }
            }
        }
    }
    private fun welcome(message: String = "Your daily rotation, wherever you are.") {
        page("YOUR NEXT SKIN AWAITS")
        label(message)
        button("Sign in with Riot", primary = true) { beginLogin() }
        button("Try loading shop") { refresh() }
        button("Sign out") { logout() }
        label("Unofficial companion. Not endorsed by Riot Games.", 12f)
    }
    private fun refresh() {
        task("LOADING YOUR SHOP", {
            val session = vault.load()
            if (session == null) "{\"status\":\"login_required\"}"
            else call("shop", filesDir.absolutePath, session)
        }) { renderShop(JSONObject(it)) }
    }
    private fun renderShop(result: JSONObject) {
        val status = result.getString("status")
        if (status == "login_required") { welcome("Sign in to see your personal daily shop."); return }
        if (status == "unavailable") { welcome("Your shop is unavailable. Please try again later."); return }
        val snapshot = result.getJSONObject("snapshot")
        page("DAILY SHOP")
        val fetched = snapshot.getDouble("fetched_at")
        label(if (status == "cached") "CACHED STORE | ${Date((fetched * 1000).toLong())}" else "LIVE STORE")
        val wallet = snapshot.getJSONObject("wallet")
        label("${wallet.getInt("valorant_points")} VP   |   ${wallet.getInt("radianite_points")} Radianite")
        val daily = snapshot.getJSONObject("daily_store")
        val remaining = (fetched + daily.getInt("seconds_remaining") - System.currentTimeMillis() / 1000).toLong().coerceAtLeast(0)
        label("Resets in ${remaining / 3600}h ${(remaining % 3600) / 60}m")
        val offers = daily.getJSONArray("offers")
        if (offers.length() == 0) label("No offers available.")
        for (i in 0 until offers.length() step 2) {
            val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            for (j in i..i + 1) {
                val card = if (j < offers.length()) offerCard(offers.getJSONObject(j)) else LinearLayout(this)
                row.addView(card, LinearLayout.LayoutParams(0, -1, 1f).apply {
                    if (j > i) leftMargin = dp(12)
                })
            }
            body.addView(row, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(12) })
        }
        val bundles = snapshot.getJSONArray("bundles")
        if (bundles.length() > 0) label("FEATURED BUNDLES", 22f)
        for (i in 0 until bundles.length()) {
            val bundle = bundles.getJSONObject(i)
            label("${bundle.getString("name")} | ${bundle.getInt("total_discounted_price")} VP")
        }
        button("Refresh shop", primary = true) { refresh() }
        button("Sign out") { logout() }
    }
    private fun beginLogin() {
        val state = UUID.randomUUID().toString()
        loginState = state
        task("OPENING RIOT", { call("login_url", state) }) { url ->
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
            CookieManager.getInstance().setAcceptThirdPartyCookies(web, false)
            web.webViewClient = object : WebViewClient() {
                override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                    val value = request.url.toString()
                    if (request.isForMainFrame && capture(value)) return true
                    return request.url.scheme != "https"
                }
                override fun doUpdateVisitedHistory(view: WebView, url: String, reload: Boolean) { capture(url) }
                override fun onPageFinished(view: WebView, url: String) { capture(url) }
                override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                    if (request.isForMainFrame && !capture(request.url.toString()) && browser != null) {
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
        closeBrowser()
        task("CONNECTING YOUR ACCOUNT", {
            val session = call("authenticate", url, state)
            vault.save(session)
            call("shop", filesDir.absolutePath, session)
        }) { renderShop(JSONObject(it)) }
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
        CookieManager.getInstance().removeAllCookies { CookieManager.getInstance().flush() }
        WebStorage.getInstance().deleteAllData()
        welcome("You have signed out.")
    }
    @Deprecated("Legacy Activity navigation")
    override fun onBackPressed() {
        if (browser != null) { closeBrowser(); welcome() }
        else if (!busy) super.onBackPressed()
    }
    override fun onDestroy() {
        closeBrowser()
        images.close()
        worker.shutdown()
        super.onDestroy()
    }
}
