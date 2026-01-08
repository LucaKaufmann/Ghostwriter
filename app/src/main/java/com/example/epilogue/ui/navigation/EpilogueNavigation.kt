package com.example.epilogue.ui.navigation

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.example.epilogue.ui.feed.FeedManagerScreen
import com.example.epilogue.ui.history.DigestDetailScreen
import com.example.epilogue.ui.history.HistoryScreen
import com.example.epilogue.ui.settings.SettingsScreen

/**
 * Navigation routes for the app.
 */
object EpilogueRoutes {
    const val FEEDS = "feeds"
    const val SETTINGS = "settings"
    const val HISTORY = "history"
    const val DIGEST_DETAIL = "digest/{digestId}"

    fun digestDetail(digestId: Long) = "digest/$digestId"
}

/**
 * Main navigation host for the app.
 */
@Composable
fun EpilogueNavHost(
    modifier: Modifier = Modifier,
    navController: NavHostController = rememberNavController(),
    startDestination: String = EpilogueRoutes.FEEDS
) {
    NavHost(
        navController = navController,
        startDestination = startDestination,
        modifier = modifier
    ) {
        composable(EpilogueRoutes.FEEDS) {
            FeedManagerScreen(
                onNavigateToSettings = {
                    navController.navigate(EpilogueRoutes.SETTINGS)
                },
                onNavigateToHistory = {
                    navController.navigate(EpilogueRoutes.HISTORY)
                }
            )
        }

        composable(EpilogueRoutes.SETTINGS) {
            SettingsScreen(
                onNavigateBack = {
                    navController.popBackStack()
                }
            )
        }

        composable(EpilogueRoutes.HISTORY) {
            HistoryScreen(
                onNavigateBack = {
                    navController.popBackStack()
                },
                onDigestClick = { digestId ->
                    navController.navigate(EpilogueRoutes.digestDetail(digestId))
                }
            )
        }

        composable(
            route = EpilogueRoutes.DIGEST_DETAIL,
            arguments = listOf(navArgument("digestId") { type = NavType.LongType })
        ) { backStackEntry ->
            val digestId = backStackEntry.arguments?.getLong("digestId") ?: return@composable
            DigestDetailScreen(
                digestId = digestId,
                onNavigateBack = {
                    navController.popBackStack()
                }
            )
        }
    }
}
