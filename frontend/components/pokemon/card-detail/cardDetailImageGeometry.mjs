const positive = (value) => {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? number : null;
};

export function getObjectContainPaintedRect({
  imageRect,
  naturalWidth,
  naturalHeight,
} = {}) {
  const elementWidth = positive(imageRect?.width);
  const elementHeight = positive(imageRect?.height);
  const sourceWidth = positive(naturalWidth);
  const sourceHeight = positive(naturalHeight);
  const left = Number(imageRect?.left);
  const top = Number(imageRect?.top);
  if (
    !elementWidth ||
    !elementHeight ||
    !sourceWidth ||
    !sourceHeight ||
    !Number.isFinite(left) ||
    !Number.isFinite(top)
  )
    return null;
  const scale = Math.min(
    elementWidth / sourceWidth,
    elementHeight / sourceHeight,
  );
  const width = sourceWidth * scale;
  const height = sourceHeight * scale;
  return {
    left: left + (elementWidth - width) / 2,
    top: top + (elementHeight - height) / 2,
    width,
    height,
  };
}
