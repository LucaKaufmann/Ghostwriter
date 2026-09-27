<script lang="ts">
	import { onMount } from 'svelte';
	import { QueryClient, QueryClientProvider } from '@tanstack/svelte-query';
	import { ModeWatcher, createInitialModeExpression } from 'mode-watcher';
	import { Toaster } from '$lib/components/ui/sonner';
	import { api, ApiError } from '$lib/api';
	import { auth, isAuthenticated, isLoading } from '$lib/stores/auth';
	import AppShell from '$lib/components/layout/AppShell.svelte';
	import LoginScreen from '$lib/components/layout/LoginScreen.svelte';
	import LoadingScreen from '$lib/components/layout/LoadingScreen.svelte';
	import './layout.css';

	let { children } = $props();

	const themeColors = {
		light: '#f8fafc',
		dark: '#0f172a'
	};

	const initialModeExpression = createInitialModeExpression({
		themeColors
	});

	// Create TanStack Query client
	const queryClient = new QueryClient({
		defaultOptions: {
			queries: {
				staleTime: 1000 * 60, // 1 minute
				retry: (failureCount, error) => {
					if (error instanceof ApiError && (error.status === 401 || error.status === 403)) return false;
					return failureCount < 3;
				}
			}
		}
	});

	onMount(() => {
		const stopUnauthorized = api.onUnauthorized((token) => auth.expireSession(token));
		let wasAuthenticated = false;
		const stopAuth = auth.subscribe((state) => {
			if (wasAuthenticated && !state.isAuthenticated) queryClient.clear();
			wasAuthenticated = state.isAuthenticated;
		});
		auth.init();
		return () => {
			stopUnauthorized();
			stopAuth();
		};
	});
</script>

<svelte:head>
	{@html `<script>${initialModeExpression}</script>`}
</svelte:head>

<QueryClientProvider client={queryClient}>
	<ModeWatcher disableHeadScriptInjection themeColors={themeColors} />
	{#if $isLoading}
		<LoadingScreen />
	{:else if !$isAuthenticated}
		<LoginScreen />
	{:else}
		<AppShell>
			{@render children()}
		</AppShell>
	{/if}
	<Toaster richColors position="top-right" />
</QueryClientProvider>
