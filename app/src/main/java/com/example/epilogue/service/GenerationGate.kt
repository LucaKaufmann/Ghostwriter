package com.example.epilogue.service

import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.sync.Mutex

/** One gate shared by scheduled, manual, retry, and regeneration workers. */
@Singleton
class GenerationGate @Inject constructor() {
    private val mutex = Mutex()

    suspend fun <T> run(block: suspend () -> T): T {
        mutex.lock()
        try {
            return block()
        } finally {
            mutex.unlock()
        }
    }
}
