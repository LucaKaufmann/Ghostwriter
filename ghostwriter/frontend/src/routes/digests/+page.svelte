<script lang="ts">
	const digestsPageModule = import('$lib/components/features/digests/DigestsPage.svelte');
</script>

{#await digestsPageModule}
	<div class="py-12 text-center text-sm text-muted-foreground">Loading digests…</div>
{:then module}
	{@const DigestsPage = module.default}
	<DigestsPage />
{/await}
