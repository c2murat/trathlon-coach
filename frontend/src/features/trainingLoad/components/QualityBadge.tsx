import type { TrainingLoadQuality } from "../../../types/trainingLoad";
import { getTrainingLoadQualityLabel } from "../../../utils/trainingLoadFormat";

export function QualityBadge({ quality }: { quality: TrainingLoadQuality }) {
  return <span className={`training-load-quality-badge training-load-quality-badge--${quality}`} data-quality={quality}>
    {getTrainingLoadQualityLabel(quality)}
  </span>;
}
