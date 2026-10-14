(() => {
  'use strict';

  const root = document.documentElement;
  const tokenIds = [
    'background', 'surface', 'surface_raised', 'primary', 'danger', 'text',
    'text_muted', 'border', 'focus', 'success', 'accent', 'hp', 'xp'
  ];
  const preview = {
    id: 'neon_preview',
    color_scheme: 'dark',
    typography_id: 'modern',
    texture_id: 'grid',
    icon_set_id: 'neutral',
    shape_id: 'cut_corner',
    tokens: [
      ['background', '#07121b'], ['surface', '#112633'],
      ['surface_raised', '#173240'], ['primary', '#31e5d7'],
      ['danger', '#ff6278'], ['text', '#eefcff'],
      ['text_muted', '#b4d6df'], ['border', '#2b98a9'],
      ['focus', '#ffe381'], ['success', '#64e0a4'],
      ['accent', '#c28eff'], ['hp', '#b12848'], ['xp', '#ffe17a']
    ].map(([id, value]) => ({ id, value }))
  };
  const initialWorldKey = root.dataset.worldKey || '';
  let activeTheme = {
    id: root.dataset.theme || 'dark_fantasy',
    color_scheme: root.classList.contains('dark') ? 'dark' : 'light',
    typography_id: root.dataset.typeface || 'classic',
    texture_id: root.dataset.texture || 'runes',
    icon_set_id: root.dataset.iconSet || 'classic',
    shape_id: root.dataset.shape || 'rounded',
    tokens: tokenIds.map(id => ({
      id,
      value: root.style.getPropertyValue(`--ui-${id.replace('_', '-')}`).trim()
    })).filter(token => token.value)
  };
  let activeWorldKey = initialWorldKey;
  let previewEnabled = false;
  let selectedWorldPreview = null;

  try {
    const lastTheme = JSON.parse(localStorage.getItem('rpg_last_world_theme') || 'null');
    if (lastTheme?.worldKey && lastTheme?.theme &&
        (!navigator.onLine || lastTheme.worldKey === initialWorldKey) &&
        applyTheme(lastTheme.theme)) {
      activeTheme = lastTheme.theme;
      activeWorldKey = lastTheme.worldKey;
      root.dataset.worldKey = activeWorldKey;
    }
  } catch (_) {}

  function applyTheme(theme) {
    if (!theme || !Array.isArray(theme.tokens)) return false;
    const values = new Map(theme.tokens.map(token => [token.id, token.value]));
    if (!tokenIds.every(id => /^#[0-9a-f]{6}$/i.test(values.get(id) || ''))) return false;
    for (const id of tokenIds) {
      root.style.setProperty(`--ui-${id.replace('_', '-')}`, values.get(id));
    }
    root.dataset.theme = theme.id;
    root.dataset.typeface = theme.typography_id;
    root.dataset.texture = theme.texture_id;
    root.dataset.iconSet = theme.icon_set_id;
    root.dataset.shape = theme.shape_id === 'cut_corner' ? 'cut_corner' : 'rounded';
    root.classList.toggle('dark', theme.color_scheme === 'dark');
    document.querySelector('meta[name="theme-color"]')?.setAttribute(
      'content', values.get('background')
    );
    document.querySelector('meta[name="background-color"]')?.setAttribute(
      'content', values.get('background')
    );
    return true;
  }

  function savedPreviewMatches(worldKey) {
    try {
      return localStorage.getItem('rpg_theme_preview') === preview.id &&
        localStorage.getItem('rpg_theme_preview_world') === worldKey;
    } catch (_) {
      return false;
    }
  }

  function applyPackTheme(theme, worldKey) {
    if (!theme || !worldKey) return;
    const worldChanged = Boolean(activeWorldKey && activeWorldKey !== worldKey);
    activeTheme = theme;
    activeWorldKey = worldKey;
    root.dataset.worldKey = worldKey;
    try {
      localStorage.setItem('rpg_last_world_theme', JSON.stringify({ worldKey, theme }));
    } catch (_) {}
    if (worldChanged) clearPreview();
    else if (selectedWorldPreview) {
      previewEnabled = applyTheme(selectedWorldPreview);
    } else if (savedPreviewMatches(worldKey)) {
      previewEnabled = true;
      applyTheme(preview);
    } else {
      previewEnabled = false;
      applyTheme(activeTheme);
    }
  }

  function showPreview() {
    if (!activeWorldKey) return;
    selectedWorldPreview = null;
    previewEnabled = true;
    try {
      localStorage.setItem('rpg_theme_preview', preview.id);
      localStorage.setItem('rpg_theme_preview_world', activeWorldKey);
    } catch (_) {}
    applyTheme(preview);
  }

  function showWorldPreview(theme) {
    if (!activeWorldKey || !applyTheme(theme)) return false;
    selectedWorldPreview = theme;
    previewEnabled = true;
    try {
      localStorage.removeItem('rpg_theme_preview');
      localStorage.removeItem('rpg_theme_preview_world');
    } catch (_) {}
    return true;
  }

  function clearPreview() {
    previewEnabled = false;
    selectedWorldPreview = null;
    try {
      localStorage.removeItem('rpg_theme_preview');
      localStorage.removeItem('rpg_theme_preview_world');
    } catch (_) {}
    applyTheme(activeTheme);
  }

  function clearWorldPreview() {
    if (selectedWorldPreview) clearPreview();
  }

  try {
    if (localStorage.getItem('rpg_theme_preview') === preview.id &&
        localStorage.getItem('rpg_theme_preview_world') !== activeWorldKey) {
      localStorage.removeItem('rpg_theme_preview');
      localStorage.removeItem('rpg_theme_preview_world');
    }
  } catch (_) {}

  if (savedPreviewMatches(activeWorldKey)) {
    previewEnabled = true;
    applyTheme(preview);
  }

  window.TTRPG_THEME = {
    applyPackTheme,
    showPreview,
    showWorldPreview,
    clearPreview,
    clearWorldPreview,
    get isPreview() { return previewEnabled; },
    get isWorldPreview() { return Boolean(selectedWorldPreview); }
  };
})();
