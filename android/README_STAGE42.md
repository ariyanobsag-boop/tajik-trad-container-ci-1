# XAU/USD PRO - Android

## Project configuration

- Android Gradle Plugin: 9.4.1
- Gradle distribution: 9.6.0
- Kotlin: 2.4.21
- Retrofit: 3.0.0
- Kotlinx Serialization JSON: 1.11.0

## Package

com.xauusdpro.android

## Modules

- app

## API source files

- app/src/main/java/com/xauusdpro/android/data/ApiModels.kt
- app/src/main/java/com/xauusdpro/android/data/MarketApi.kt

## Current state

This is an initial Android project skeleton.

The application does not connect to a broker.
It does not submit, modify, or close orders.
It does not execute trades automatically.

The API client has not yet been initialized.

The API server is currently a local development service.
A real Android device cannot access the Colab localhost address directly.

Before enabling remote API access, a secure reachable server endpoint
and appropriate HTTPS configuration are required.

## Build requirement

- JDK 17
- Gradle 9.6.0
- Android SDK platform 36

## Next stage

Validate Gradle wrapper, Android SDK availability,
Kotlin compilation, and API client dependencies.
