import { ParsedOverlayCommand } from './CompanionManager';

export interface FibonacciGrid {
  swingHigh: number;
  swingLow: number;
  level382: number;
  level500: number;
  level618: number;
  riskRewardRatio: string;
}

/**
 * Financial Chart, Candlesticks, Fibonacci & Risk-Reward Visual Analyst.
 *
 * Merge note: zone BOXes are conceptual diagram zones (support/resistance),
 * so the standard left-zone claim/clamp machinery applies - unlike the
 * AppScanner/translator, these never point at a real screen control.
 * Numbers in the prompt become the swing high/low; defaults only kick in
 * when no usable range is given. Educational risk framing only.
 */
export class ChartPatternTutor {
  public static isChartPrompt(prompt: string): boolean {
    return /\b(chart\s+pattern|candlestick|tradingview|fibonacci|support\s+and\s+resistance|price\s+action|breakout|risk\s+reward|macd|rsi|market\s+structure)\b/i.test(prompt);
  }

  public static calculateFibonacciLevels(high: number = 25200, low: number = 24400): FibonacciGrid {
    const diff = high - low;
    return {
      swingHigh: high,
      swingLow: low,
      level382: Number((high - diff * 0.382).toFixed(2)),
      level500: Number((high - diff * 0.5).toFixed(2)),
      level618: Number((high - diff * 0.618).toFixed(2)),
      riskRewardRatio: '1 : 2.8',
    };
  }

  public static buildChartAnalystOverlay(userPrompt: string): ParsedOverlayCommand[] {
    const nums = (userPrompt.match(/\b\d+(?:\.\d+)?\b/g) || []).map(Number).filter((n) => n > 10);
    const high = nums.length >= 2 ? Math.max(nums[0], nums[1]) : 25200;
    const low = nums.length >= 2 ? Math.min(nums[0], nums[1]) : 24400;
    const fib = this.calculateFibonacciLevels(high, low);

    return [
      { type: 'BOARD', label: `Financial Chart Visual Analyst • Range [${fib.swingLow} – ${fib.swingHigh}]` },
      {
        type: 'BOX',
        x: 180,
        y: 140,
        w: 480,
        h: 36,
        label: `Major Resistance / Supply Zone (${fib.swingHigh})`,
        color: 'red',
      },
      {
        type: 'BOX',
        x: 180,
        y: 250,
        w: 480,
        h: 42,
        label: `Golden Pocket Fib 0.618 Pullback Zone (${fib.level618})`,
        color: 'yellow',
      },
      {
        type: 'BOX',
        x: 180,
        y: 360,
        w: 480,
        h: 36,
        label: `Institutional Demand / Support Base (${fib.swingLow})`,
        color: 'green',
      },
      {
        type: 'WRITE',
        label: `Fibonacci Retracements: 38.2% = ${fib.level382} | 50.0% = ${fib.level500} | 61.8% = ${fib.level618}`,
        color: 'cyan',
      },
      {
        type: 'WRITE',
        label: 'Candlestick Confluence: Wait for a high-volume bullish engulfing or hammer rejection wick inside the 0.618 zone.',
        color: 'yellow',
      },
      {
        type: 'WRITE',
        label: `Risk Management (Educational): Target R:R = ${fib.riskRewardRatio} with invalidation below ${fib.swingLow}.`,
        color: 'green',
      },
    ];
  }
}
