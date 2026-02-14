<script lang="ts">
	const feedsPageModule = import('$lib/components/features/feeds/FeedsPage.svelte');
</script>

{#await feedsPageModule}
	<div class="py-12 text-center text-sm text-muted-foreground">Loading feeds…</div>
{:then module}
	{@const FeedsPage = module.default}
	<FeedsPage />
{/await}
