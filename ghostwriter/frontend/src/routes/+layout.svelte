<script lang="ts">
	import { onMount } from 'svelte';
	import { QueryClient, QueryClientProvider } from '@tanstack/svelte-query';
	import { Toaster } from '$lib/components/ui/sonner';
	import { auth, isAuthenticated, isLoading } from '$lib/stores/auth';
	import AppShell from '$lib/components/layout/AppShell.svelte';
	import LoginScreen from '$lib/components/layout/LoginScreen.svelte';
	import LoadingScreen from '$lib/components/layout/LoadingScreen.svelte';
	import './layout.css';

	let { children } = $props();

	// Create TanStack Query client
	const queryClient = new QueryClient({
		defaultOptions: {
			queries: {
				staleTime: 1000 * 60, // 1 minute
				retry: (failureCount, error) => {
					// Don't retry on auth errors
					if (error instanceof Error && error.message.includes('401')) {
						return false;
					}
					return failureCount < 3;
				}
			}
		}
	});

	// Debug: log reactive state changes
	$effect(() => {
		console.log('[layout] state:', { isLoading: $isLoading, isAuthenticated: $isAuthenticated });
	});

	onMount(() => {
		console.log('[layout] onMount, calling auth.init()');
		auth.init();
	});
</script>

<QueryClientProvider client={queryClient}>
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
