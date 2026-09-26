plugins {
    id("com.android.application")
    id("com.chaquo.python")
}

android {
    namespace = "org.botcautomod.host"
    compileSdk = 36

    defaultConfig {
        applicationId = "org.botcautomod.host"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
        ndk {
            abiFilters += listOf("arm64-v8a", "x86_64")   // phones, and the emulator
        }
    }

    // llama-server (from fetch_llama.sh) must be unpacked on install so it can be run.
    packaging {
        jniLibs {
            useLegacyPackaging = true
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }
}

chaquopy {
    defaultConfig {
        version = "3.12"
        // A Python 3.12 on the build machine. Set BOTC_BUILD_PYTHON if it is not on PATH.
        buildPython(System.getenv("BOTC_BUILD_PYTHON") ?: "python3.12")
        pip {
            // All pure Python, so they install for any Android ABI.
            install("starlette")
            install("uvicorn")
            install("wsproto")
            install("segno")
        }
        // The server reads its web pages and character data from files next to the code.
        extractPackages("botc_automod")
    }
    sourceSets {
        getByName("main") {
            srcDir("../../src")   // the same botc_automod package the desktop runs
        }
    }
}
