<script lang="ts">
	const episodesPageModule = import('$lib/components/features/episodes/EpisodesPage.svelte');
</script>

{#await episodesPageModule}
	<div class="py-12 text-center text-sm text-muted-foreground">Loading episodes…</div>
{:then module}
	{@const EpisodesPage = module.default}
	<EpisodesPage />
{/await}
