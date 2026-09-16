package vn.shopchecker

import android.app.Activity
import android.graphics.Color
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
    private val worker = Executors.newSingleThreadExecutor()
    private lateinit var vault: SessionVault
    private lateinit var body: LinearLayout
    private var browser: WebView? = null
    private var loginState: String? = null
    private var busy = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        vault = SessionVault(this)
        refresh()
    }
    private fun page(title: String) {
        body = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(32, 40, 32, 32)
            setBackgroundColor(Color.rgb(15, 25, 35))
        }
        setContentView(ScrollView(this).apply { addView(body) })
        label(title, 26f)
    }
    private fun label(value: String, size: Float = 17f) {
        body.addView(TextView(this).apply {
            text = value; textSize = size; setTextColor(Color.WHITE); setPadding(0, 16, 0, 16)
        })
    }
    private fun button(title: String, action: () -> Unit) {
        body.addView(Button(this).apply { text = title; setOnClickListener { action() } })
    }
    private fun call(name: String, vararg args: Any): String {
        if (!Python.isStarted()) Python.start(AndroidPlatform(applicationContext))
        return Python.getInstance().getModule("android_bridge").callAttr(name, *args).toString()
    }
    private fun task(message: String, work: () -> String, done: (String) -> Unit) {
        if (busy) return
        busy = true
        page(message)
        body.addView(ProgressBar(this))
        worker.execute {
            try {
                val result = work()
                runOnUiThread { busy = false; if (!isDestroyed) done(result) }
            } catch (_: Exception) {
                // Never expose a Python exception: it can contain account data or tokens.
                runOnUiThread {
                    busy = false
                    if (!isDestroyed) welcome("Khong ket noi duoc. Kiem tra mang va thu dang nhap lai.")
                }
            }
        }
    }
    private fun welcome(message: String = "Xem Daily Shop tren dien thoai") {
        page("Shop Checker")
        label(message)
        button("Dang nhap Riot") { beginLogin() }
        button("Thu tai shop") { refresh() }
        button("Dang xuat") { logout() }
        label("Ung dung ca nhan, khong duoc Riot bao chung.", 12f)
    }
    private fun refresh() {
        task("Dang tai shop...", {
            val session = vault.load()
            if (session == null) "{\"status\":\"login_required\"}"
            else call("shop", filesDir.absolutePath, session)
        }) { renderShop(JSONObject(it)) }
    }
    private fun renderShop(result: JSONObject) {
        val status = result.getString("status")
        if (status == "login_required") { welcome("Dang nhap de xem shop cua ban."); return }
        if (status == "unavailable") { welcome("Chua tai duoc shop. Hay thu lai sau."); return }
        val snapshot = result.getJSONObject("snapshot")
        page("Daily Shop")
        val fetched = snapshot.getDouble("fetched_at")
        label(if (status == "cached") "DU LIEU DA LUU ? ${Date((fetched * 1000).toLong())}" else "Vua cap nhat")
        val wallet = snapshot.getJSONObject("wallet")
        label("${wallet.getInt("valorant_points")} VP   |   ${wallet.getInt("radianite_points")} Radianite")
        val daily = snapshot.getJSONObject("daily_store")
        val remaining = (fetched + daily.getInt("seconds_remaining") - System.currentTimeMillis() / 1000).toLong().coerceAtLeast(0)
        label("Doi shop sau: ${remaining / 3600} gio ${(remaining % 3600) / 60} phut")
        val offers = daily.getJSONArray("offers")
        if (offers.length() == 0) label("Chua co danh sach vat pham.")
        for (i in 0 until offers.length()) {
            val offer = offers.getJSONObject(i)
            val cost = offer.getInt("cost")
            label(offer.getString("name"), 22f)
            label("${offer.getString("content_tier_name")} | ${if (cost > 0) "$cost VP" else "Chua ro gia"}")
        }
        val bundles = snapshot.getJSONArray("bundles")
        for (i in 0 until bundles.length()) {
            val bundle = bundles.getJSONObject(i)
            label("${bundle.getString("name")} ? ${bundle.getInt("total_discounted_price")} VP")
        }
        button("Lam moi") { refresh() }
        button("Dang xuat") { logout() }
    }
    private fun beginLogin() {
        val state = UUID.randomUUID().toString()
        loginState = state
        task("Dang mo Riot...", { call("login_url", state) }) { url ->
            page("Dang nhap Riot")
            button("Huy dang nhap") { closeBrowser(); welcome() }
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
                        closeBrowser(); welcome("Khong mo duoc Riot. Kiem tra mang hoac thu lai.")
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
        task("Dang ket noi tai khoan...", {
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
    }
    private fun logout() {
        if (busy) return
        closeBrowser()
        vault.clear()
        CookieManager.getInstance().removeAllCookies { CookieManager.getInstance().flush() }
        WebStorage.getInstance().deleteAllData()
        welcome("Da dang xuat.")
    }
    @Deprecated("Legacy Activity navigation")
    override fun onBackPressed() {
        if (browser != null) { closeBrowser(); welcome() }
        else if (!busy) super.onBackPressed()
    }
    override fun onDestroy() {
        closeBrowser()
        worker.shutdown()
        super.onDestroy()
    }
}
