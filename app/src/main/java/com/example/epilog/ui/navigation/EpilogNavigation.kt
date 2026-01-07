package com.example.epilog.ui.navigation

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.example.epilog.ui.feed.FeedManagerScreen
import com.example.epilog.ui.history.DigestDetailScreen
import com.example.epilog.ui.history.HistoryScreen
import com.example.epilog.ui.settings.SettingsScreen

/**
 * Navigation routes for the app.
 */
object EpilogRoutes {
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
fun EpilogNavHost(
    modifier: Modifier = Modifier,
    navController: NavHostController = rememberNavController(),
    startDestination: String = EpilogRoutes.FEEDS
) {
    NavHost(
        navController = navController,
        startDestination = startDestination,
        modifier = modifier
    ) {
        composable(EpilogRoutes.FEEDS) {
            FeedManagerScreen(
                onNavigateToSettings = {
                    navController.navigate(EpilogRoutes.SETTINGS)
                },
                onNavigateToHistory = {
                    navController.navigate(EpilogRoutes.HISTORY)
                }
            )
        }

        composable(EpilogRoutes.SETTINGS) {
            SettingsScreen(
                onNavigateBack = {
                    navController.popBackStack()
                }
            )
        }

        composable(EpilogRoutes.HISTORY) {
            HistoryScreen(
                onNavigateBack = {
                    navController.popBackStack()
                },
                onDigestClick = { digestId ->
                    navController.navigate(EpilogRoutes.digestDetail(digestId))
                }
            )
        }

        composable(
            route = EpilogRoutes.DIGEST_DETAIL,
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
