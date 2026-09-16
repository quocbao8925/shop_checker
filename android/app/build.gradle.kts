plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}
android {
    namespace = "vn.shopchecker"
    compileSdk = 35
    defaultConfig {
        applicationId = "vn.shopchecker.personal"
        minSdk = 24
        targetSdk = 34
        versionCode = 2
        versionName = "0.2.0"
        ndk { abiFilters += listOf("arm64-v8a", "x86_64") }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}
val stagePython by tasks.registering(Sync::class) {
    from("../..") {
        include("models.py", "android_bridge.py", "api/**/*.py", "auth/**/*.py", "cache/**/*.py", "assets/*.json")
    }
    into(layout.buildDirectory.dir("pythonSource"))
}
chaquopy {
    defaultConfig {
        version = "3.10"
        pip { install("requests==2.32.3") }
    }
    sourceSets.getByName("main") { srcDir(layout.buildDirectory.dir("pythonSource")) }
}
tasks.configureEach {
    if (name.contains("Python") && name != "stagePython") dependsOn(stagePython)
}
