
// Landing Page JavaScript

document.addEventListener('DOMContentLoaded', function () {
    // Smooth scrolling for navigation links
    const navLinks = document.querySelectorAll('.nav-link[href^="#"]');
    navLinks.forEach(link => {
        link.addEventListener('click', function (e) {
            e.preventDefault();
            const targetId = this.getAttribute('href');
            const targetSection = document.querySelector(targetId);

            if (targetSection) {
                targetSection.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });

    // Hero section click handler - redirect to signup on hero click
    const heroSection = document.getElementById('hero');
    if (heroSection) {
        heroSection.style.cursor = 'pointer';
        heroSection.addEventListener('click', function (e) {
            // Don't redirect if clicking on a button or link
            if (!e.target.closest('a') && !e.target.closest('button')) {
                window.location.href = '/dashboard'; // Redirecting to dashboard instead of signup for this app
            }
        });
    }

    // Animated counter for stats
    const animateCounter = (element, target, duration = 2000) => {
        const start = 0;
        const increment = target / (duration / 16);
        let current = start;

        const timer = setInterval(() => {
            current += increment;
            if (current >= target) {
                element.textContent = formatStatValue(target);
                clearInterval(timer);
            } else {
                element.textContent = formatStatValue(Math.floor(current));
            }
        }, 16);
    };

    const formatStatValue = (value) => {
        if (value >= 10000) {
            return (value / 1000).toFixed(0) + 'K+';
        }
        return value.toString();
    };

    // Intersection Observer for scroll animations
    const observerOptions = {
        threshold: 0.2,
        rootMargin: '0px 0px -100px 0px'
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.opacity = '1';
                entry.target.style.transform = 'translateY(0)';

                // Animate stats when they come into view
                if (entry.target.classList.contains('hero-stats')) {
                    const statValues = entry.target.querySelectorAll('.stat-value');
                    statValues.forEach((stat, index) => {
                        const text = stat.textContent;
                        if (text.includes('K+')) {
                            setTimeout(() => animateCounter(stat, 10000), index * 200);
                        } else if (text.includes('%')) {
                            const num = parseInt(text);
                            setTimeout(() => {
                                let current = 0;
                                const timer = setInterval(() => {
                                    current += 1;
                                    stat.textContent = current + '%';
                                    if (current >= num) clearInterval(timer);
                                }, 20);
                            }, index * 200);
                        } else if (text.includes('s')) {
                            const num = parseFloat(text);
                            setTimeout(() => {
                                let current = 0;
                                const timer = setInterval(() => {
                                    current += 0.1;
                                    stat.textContent = current.toFixed(1) + 's';
                                    if (current >= num) clearInterval(timer);
                                }, 30);
                            }, index * 200);
                        }
                    });
                }
            }
        });
    }, observerOptions);

    // Observe elements for animation
    const animatedElements = document.querySelectorAll('.feature-card, .step-card, .hero-stats');
    animatedElements.forEach(el => {
        el.style.opacity = '0';
        el.style.transform = 'translateY(30px)';
        el.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
        observer.observe(el);
    });

    // Parallax effect for gradient orbs
    window.addEventListener('scroll', () => {
        const scrolled = window.pageYOffset;
        const orbs = document.querySelectorAll('.gradient-orb');

        orbs.forEach((orb, index) => {
            const speed = 0.5 + (index * 0.1);
            orb.style.transform = `translateY(${scrolled * speed}px)`;
        });
    });
});
