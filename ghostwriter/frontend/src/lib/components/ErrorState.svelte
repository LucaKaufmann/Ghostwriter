<script lang="ts">
	import { Button } from '$lib/components/ui/button';
	import { AlertCircle, RefreshCw } from 'lucide-svelte';

	interface Props {
		message?: string;
		onRetry?: () => void;
	}

	let { message = 'Something went wrong', onRetry }: Props = $props();
</script>

<div class="flex flex-col items-center justify-center py-12 text-center">
	<div class="rounded-full bg-destructive/10 p-3">
		<AlertCircle class="h-8 w-8 text-destructive" />
	</div>
	<h3 class="mt-4 text-lg font-semibold">Error</h3>
	<p class="mt-2 max-w-md text-sm text-muted-foreground">{message}</p>
	{#if onRetry}
		<Button variant="outline" class="mt-4" onclick={onRetry}>
			<RefreshCw class="mr-2 h-4 w-4" />
			Try Again
		</Button>
	{/if}
</div>
