function logger(...args) {
  console.log('[TTRPG]', ...args);
}

function composeFeatures(...parts) {
  const descriptors = parts.reduce(
    (combined, part) => Object.assign(combined, Object.getOwnPropertyDescriptors(part)),
    {}
  );
  return Object.defineProperties({}, descriptors);
}

document.addEventListener('alpine:init', () => {
  const features = window.TTRPG_FEATURES;
  features.registerLocalComponents(Alpine);

  Alpine.data('rpgGame', () => composeFeatures(
    features.createCoreFeature(),
    features.pwaNotifications,
    features.authAdmin,
    features.sessionCharacter,
    features.storyMapProxy,
    features.realtimeChat,
    features.campaignActions,
    features.equipmentImages,
    features.market
  ));
});
