package com.example.epilog.ui.navigation

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.example.epilog.ui.feed.FeedManagerScreen
import com.example.epilog.ui.settings.SettingsScreen

/**
 * Navigation routes for the app.
 */
object EpilogRoutes {
    const val FEEDS = "feeds"
    const val SETTINGS = "settings"
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
    }
}
