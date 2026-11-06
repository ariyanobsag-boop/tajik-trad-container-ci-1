plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.serialization")
}

val configuredApiBaseUrl = (providers.gradleProperty("API_BASE_URL").orNull ?: "")
    .replace("\\", "\\\\")
    .replace("\"", "\\\"")

android {
    namespace = "com.xauusdpro.android"

    compileSdk = 36

    defaultConfig {
        applicationId = "com.xauusdpro.android"

        minSdk = 26
        targetSdk = 36

        versionCode = 1
        versionName = "0.1.0"
        buildConfigField("String", "API_BASE_URL", "\"$configuredApiBaseUrl\"")
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        buildConfig = true
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(
            org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
        )
    }
}

dependencies {
    implementation(
        "com.squareup.retrofit2:retrofit:3.0.0"
    )
    implementation("com.squareup.retrofit2:converter-kotlinx-serialization:3.0.0")

    implementation(
        "org.jetbrains.kotlinx:kotlinx-serialization-json:1.11.0"
    )
}
