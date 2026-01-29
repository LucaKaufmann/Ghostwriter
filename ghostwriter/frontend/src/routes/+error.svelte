<script lang="ts">
	import { page } from '$app/stores';
	import { Button } from '$lib/components/ui/button';
	import { AlertCircle, Home, RefreshCw } from 'lucide-svelte';
</script>

<svelte:head>
	<title>Error - Ghostwriter</title>
</svelte:head>

<div class="flex min-h-[80vh] flex-col items-center justify-center px-4 text-center">
	<div class="rounded-full bg-destructive/10 p-4">
		<AlertCircle class="h-12 w-12 text-destructive" />
	</div>
	
	<h1 class="mt-6 text-2xl font-bold">
		{#if $page.status === 404}
			Page Not Found
		{:else}
			Something went wrong
		{/if}
	</h1>
	
	<p class="mt-2 max-w-md text-muted-foreground">
		{#if $page.status === 404}
			The page you're looking for doesn't exist or has been moved.
		{:else if $page.error?.message}
			{$page.error.message}
		{:else}
			An unexpected error occurred. Please try again.
		{/if}
	</p>
	
	<div class="mt-6 flex gap-3">
		<Button variant="outline" onclick={() => window.location.reload()}>
			<RefreshCw class="mr-2 h-4 w-4" />
			Refresh
		</Button>
		<Button href="/">
			<Home class="mr-2 h-4 w-4" />
			Go Home
		</Button>
	</div>
</div>
