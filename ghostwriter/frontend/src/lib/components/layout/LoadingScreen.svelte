<script lang="ts">
	import { Loader2 } from 'lucide-svelte';
</script>

<div class="flex min-h-screen items-center justify-center bg-background">
	<div class="flex flex-col items-center gap-4">
		<Loader2 class="h-8 w-8 animate-spin text-muted-foreground" />
		<p class="text-sm text-muted-foreground">Loading...</p>
	</div>
</div>
