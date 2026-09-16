package vn.shopchecker

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.os.Handler
import android.os.Looper
import android.util.LruCache
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

/** Bounded background downloads; decoded images are reused while the app is open. */
class SkinImages {
    private val executor = Executors.newFixedThreadPool(2)
    private val main = Handler(Looper.getMainLooper())
    @Volatile private var closed = false
    private val cache = object : LruCache<String, Bitmap>(12 * 1024 * 1024) {
        override fun sizeOf(key: String, value: Bitmap) = value.byteCount
    }

    fun load(address: String, callback: (Bitmap?) -> Unit) {
        if (closed) return
        cache.get(address)?.let { callback(it); return }
        executor.execute {
            val bitmap = try { download(address) } catch (_: Exception) { null }
            if (!closed) {
                if (bitmap != null) cache.put(address, bitmap)
                main.post { if (!closed) callback(bitmap) }
            }
        }
    }

    private fun download(address: String): Bitmap? {
        if (address.isBlank()) return null
        val url = URL(address)
        if (url.protocol != "https") return null
        val connection = url.openConnection() as HttpURLConnection
        try {
            connection.connectTimeout = 10000
            connection.readTimeout = 10000
            connection.instanceFollowRedirects = false
            if (connection.responseCode != 200) return null
            val bytes = connection.inputStream.use { input ->
                val output = ByteArrayOutputStream()
                val buffer = ByteArray(8192)
                while (true) {
                    val count = input.read(buffer)
                    if (count < 0) break
                    if (output.size() + count > 8 * 1024 * 1024) return null
                    output.write(buffer, 0, count)
                }
                output.toByteArray()
            }
            val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
            BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
            if (bounds.outWidth <= 0 || bounds.outHeight <= 0) return null
            var sample = 1
            while (bounds.outWidth / sample > 1024 || bounds.outHeight / sample > 1024) sample *= 2
            return BitmapFactory.decodeByteArray(bytes, 0, bytes.size,
                BitmapFactory.Options().apply { inSampleSize = sample })
        } finally {
            connection.disconnect()
        }
    }

    fun close() {
        closed = true
        executor.shutdownNow()
        main.removeCallbacksAndMessages(null)
        cache.evictAll()
    }
}
