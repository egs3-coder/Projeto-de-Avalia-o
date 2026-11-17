package br.com.projetointegrador.estoque;

import io.micrometer.observation.ObservationPredicate;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.aop.ObservedAspect;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.server.observation.ServerRequestObservationContext;

@SpringBootApplication
public class EstoqueApplication {

    public static void main(String[] args) {
        SpringApplication.run(EstoqueApplication.class, args);
    }

    /** Habilita a anotação @Observed: cada método anotado vira um span e uma métrica. */
    @Bean
    ObservedAspect observedAspect(ObservationRegistry registry) {
        return new ObservedAspect(registry);
    }

    /**
     * Não gera traces/métricas HTTP para as chamadas do Prometheus em /actuator/**
     * (scrape a cada 15 s), evitando poluir o Tempo com traces sem valor.
     */
    @Bean
    ObservationPredicate ignorarActuator() {
        return (name, context) -> {
            if (context instanceof ServerRequestObservationContext servidor) {
                return !servidor.getCarrier().getRequestURI().startsWith("/actuator");
            }
            return true;
        };
    }
}
