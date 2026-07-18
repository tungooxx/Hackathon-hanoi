import { useEffect, useState, useCallback } from 'react'
import { carouselSlides } from '../data/categories'

export default function Carousel() {
  const [index, setIndex] = useState(0)
  const count = carouselSlides.length

  const go = useCallback(
    (next) => setIndex((i) => (next + count) % count),
    [count],
  )

  // Auto-slide every 5s
  useEffect(() => {
    const id = setInterval(() => {
      setIndex((i) => (i + 1) % count)
    }, 5000)
    return () => clearInterval(id)
  }, [count])

  return (
    <div className="carousel">
      <div className="carousel__viewport">
        <div
          className="carousel__track"
          style={{ transform: `translateX(-${index * 100}%)` }}
        >
          {carouselSlides.map((src, i) => (
            <div className="carousel__slide" key={i}>
              <img src={src} alt={`Khuyến mãi ${i + 1}`} draggable="false" />
            </div>
          ))}
        </div>

        <button
          className="carousel__arrow carousel__arrow--prev"
          onClick={() => go(index - 1)}
          aria-label="Trước"
        >
          ‹
        </button>
        <button
          className="carousel__arrow carousel__arrow--next"
          onClick={() => go(index + 1)}
          aria-label="Sau"
        >
          ›
        </button>
      </div>

      <div className="carousel__dots">
        {carouselSlides.map((_, i) => (
          <button
            key={i}
            className={`carousel__dot ${i === index ? 'carousel__dot--active' : ''}`}
            onClick={() => setIndex(i)}
            aria-label={`Slide ${i + 1}`}
          />
        ))}
      </div>
    </div>
  )
}
